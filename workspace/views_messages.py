"""Compose and send SMS / email from the workspace, and the message history."""
from collections import Counter

from django import forms
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse

from app.admin import CustomMembershipEmailForm

from . import messaging, sms
from .access import can, render_ws, workspace_view
from .models import MessageLog
from .views import PAGE_SIZES, _page, _query_without

MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024


class MessageForm(forms.Form):
    channel = forms.ChoiceField(choices=MessageLog.CHANNEL_CHOICES)
    sms_text = forms.CharField(required=False, max_length=1000, widget=forms.Textarea(attrs={'rows': 5}))
    sender = forms.ChoiceField(choices=CustomMembershipEmailForm.SENDER_CHOICES, initial='uztea')
    template = forms.ChoiceField(choices=CustomMembershipEmailForm.TEMPLATE_CHOICES, initial='uztea_brand')
    subject = forms.CharField(required=False, max_length=255)
    body = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 10}))
    is_html = forms.BooleanField(required=False)
    confirm = forms.BooleanField(required=True, error_messages={'required': 'Tick the box to confirm sending.'})

    def clean(self):
        data = super().clean()
        if data.get('channel') == MessageLog.CHANNEL_SMS and not (data.get('sms_text') or '').strip():
            self.add_error('sms_text', 'Write the SMS text.')
        if data.get('channel') == MessageLog.CHANNEL_EMAIL:
            if not (data.get('subject') or '').strip():
                self.add_error('subject', 'Write a subject.')
            if not (data.get('body') or '').strip():
                self.add_error('body', 'Write the message.')
        return data


def _back_url(source):
    return {
        'member': reverse('workspace:people'), 'teachers_bank': reverse('workspace:teachers_bank'),
        'partner': reverse('workspace:partners'), 'tesol': reverse('workspace:forms'),
        'anniversary': reverse('workspace:forms'),
    }.get(source, reverse('workspace:people'))


@workspace_view('people', 'workspace.add_messagelog')
def compose(request):
    source = request.GET.get('source') or request.POST.get('source') or 'member'
    if not messaging.can_send(request.user, source):
        return render_ws(request, 'workspace/forbidden.html', {}, 'people', status=403)

    raw_ids = request.POST.getlist('_selected_action') or request.POST.getlist('ids') or request.GET.getlist('ids')
    ids = messaging.parse_ids(raw_ids)
    people = messaging.recipients(source, ids)
    back = _back_url(source)
    if not people:
        messages.warning(request, 'Select at least one person first.')
        return redirect(back)

    channel = request.POST.get('channel') or request.GET.get('channel') or MessageLog.CHANNEL_EMAIL
    sending = request.method == 'POST' and request.POST.get('step') == 'send'
    form = MessageForm(request.POST if sending else None, initial={'channel': channel})
    sms_mode = messaging.sms_mode()

    if sending and form.is_valid():
        data = form.cleaned_data
        files = request.FILES.getlist('attachments')
        too_big = [f.name for f in files if f.size > MAX_ATTACHMENT_SIZE]
        if too_big:
            form.add_error(None, f"Attachments over 5 MB: {', '.join(too_big)}")
        elif data['channel'] == MessageLog.CHANNEL_SMS and sms_mode == 'off':
            form.add_error(None, 'SMS is not configured on this server (Eskiz credentials are missing).')
        else:
            try:
                if data['channel'] == MessageLog.CHANNEL_SMS:
                    batch = messaging.send_sms_batch(request.user, source, people, data['sms_text'].strip())
                else:
                    attachments = [(f.name, f.read(), f.content_type) for f in files]
                    batch = messaging.send_email_batch(
                        request.user, source, people, subject=data['subject'].strip(), body=data['body'],
                        is_html=data['is_html'], sender=data['sender'], template=data['template'],
                        attachments=attachments)
            except Exception as exc:
                form.add_error(None, f'Nothing was sent: {exc}')
            else:
                counts = Counter(MessageLog.objects.filter(batch=batch).values_list('status', flat=True))
                summary = ', '.join(f'{n} {dict(MessageLog.STATUS_CHOICES)[s].lower()}' for s, n in counts.items())
                messages.success(request, f'Done: {summary}.')
                return redirect(reverse('workspace:messages') + f'?batch={batch}')

    with_phone = sum(1 for p in people if p['phone'])
    with_email = sum(1 for p in people if p['email'] and not p.get('unsubscribed'))
    unsubscribed = sum(1 for p in people if p.get('unsubscribed'))
    label = messaging.SOURCES[source][0]
    return render_ws(request, 'workspace/messages/compose.html', {
        'page_title': 'Send message',
        'form': form, 'channel': form.data.get('channel', channel) if sending else channel,
        'source': source, 'source_label': label, 'people': people, 'shown_people': people[:50],
        'total': len(people), 'with_phone': with_phone, 'with_email': with_email, 'unsubscribed': unsubscribed,
        'max_recipients': messaging.MAX_RECIPIENTS, 'truncated': len(ids) > messaging.MAX_RECIPIENTS,
        'sms_mode': sms_mode, 'sms_sender': sms.config()['sender'],
        'email_console': messaging.email_is_console(),
        'placeholders': messaging.PLACEHOLDERS if source == 'member' else messaging.PLACEHOLDERS[:1],
        'back_url': back,
    }, 'partners' if source == 'partner' else 'people')


@workspace_view('people', 'workspace.view_messagelog')
def history(request):
    qs = MessageLog.objects.select_related('sent_by')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(recipient_name__icontains=q) | Q(to__icontains=q) | Q(subject__icontains=q) | Q(body__icontains=q))
    for key in ('channel', 'status', 'source'):
        if request.GET.get(key):
            qs = qs.filter(**{key: request.GET[key]})
    batch = request.GET.get('batch', '')
    batch_counts = None
    if batch:
        try:
            qs = qs.filter(batch=batch)
            batch_counts = Counter(qs.values_list('status', flat=True))
        except Exception:
            qs = qs.none()
    page, per_page = _page(request, qs)
    user = request.user
    return render_ws(request, 'workspace/messages/history.html', {
        'page_title': 'People',
        'page_subtitle': 'SMS and email sent from the workspace',
        'people_tab': 'messages',
        'can_all': can(user, 'app.view_membership'), 'can_pending': can(user, 'app.view_pendingpayment'),
        'can_teachers_bank': can(user, 'app.view_teacherbank'),
        'page': page, 'per_page': per_page, 'page_sizes': PAGE_SIZES, 'total': page.paginator.count,
        'q': q, 'filters': request.GET, 'batch': batch,
        'batch_counts': [(dict(MessageLog.STATUS_CHOICES)[k], k, v) for k, v in (batch_counts or {}).items()],
        'channel_options': MessageLog.CHANNEL_CHOICES, 'status_options': MessageLog.STATUS_CHOICES,
        'source_options': [(k, v[0]) for k, v in messaging.SOURCES.items()],
        'base_query': _query_without(request, 'page'),
    }, 'people')
