"""Events (Forms & Events → Events) and member benefits (Partners → Benefits)."""
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from .access import can, render_ws, workspace_view
from .models import Benefit, Event
from .people import membership_type_options
from .views import PAGE_SIZES, _page


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'kind', 'starts_at', 'ends_at', 'location', 'registration_url', 'description',
                  'is_published', 'members_only']
        widgets = {
            'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'ends_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'description': forms.Textarea(attrs={'rows': 5}),
        }

    def clean(self):
        data = super().clean()
        if data.get('starts_at') and data.get('ends_at') and data['ends_at'] < data['starts_at']:
            self.add_error('ends_at', 'The end must be after the start.')
        return data


class BenefitForm(forms.ModelForm):
    membership_type_list = forms.MultipleChoiceField(
        required=False, label='Who gets it', widget=forms.CheckboxSelectMultiple,
        help_text='Leave empty for every active member.')

    class Meta:
        model = Benefit
        fields = ['title', 'partner', 'discount', 'code', 'link', 'valid_until', 'description', 'is_active']
        widgets = {'valid_until': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'description': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['membership_type_list'].choices = membership_type_options()
        if self.instance.pk:
            self.initial['membership_type_list'] = self.instance.type_codes()

    def save(self, commit=True):
        self.instance.membership_types = ','.join(self.cleaned_data.get('membership_type_list') or [])
        return super().save(commit)


def _edit(request, model, form_class, pk, section, list_url, template, title):
    obj = get_object_or_404(model, pk=pk) if pk else None
    perm = f"workspace.{'change' if obj else 'add'}_{model._meta.model_name}"
    if not request.user.has_perm(perm):
        return render_ws(request, 'workspace/forbidden.html', {}, section, status=403)
    form = form_class(request.POST or None, instance=obj)
    if request.method == 'POST':
        if request.POST.get('delete') and obj and request.user.has_perm(f'workspace.delete_{model._meta.model_name}'):
            obj.delete()
            messages.success(request, f'Deleted "{obj}".')
            return redirect(list_url)
        if form.is_valid():
            saved = form.save()
            messages.success(request, f'Saved "{saved}".')
            return redirect(list_url)
    return render_ws(request, template, {
        'page_title': title, 'form': form, 'obj': obj, 'list_url': list_url,
        'can_delete': obj and request.user.has_perm(f'workspace.delete_{model._meta.model_name}'),
    }, section)


@workspace_view('forms', 'workspace.view_event')
def events_list(request):
    from django.urls import reverse
    when = request.GET.get('when', 'upcoming')
    qs = Event.objects.all()
    now = timezone.now()
    if when == 'past':
        qs = qs.filter(starts_at__lt=now).order_by('-starts_at')
    elif when == 'upcoming':
        qs = qs.filter(starts_at__gte=now)
    page, per_page = _page(request, qs)
    return render_ws(request, 'workspace/events/list.html', {
        'page_title': 'Forms & Events', 'page_subtitle': 'Events shown to members in their cabinet',
        'page': page, 'per_page': per_page, 'page_sizes': PAGE_SIZES, 'when': when,
        'add_url': reverse('workspace:event_add') if can(request.user, 'workspace.add_event') else None,
        'can_edit': can(request.user, 'workspace.change_event'),
    }, 'forms')


@workspace_view('forms', 'workspace.add_event', 'workspace.change_event')
def event_edit(request, pk=None):
    from django.urls import reverse
    return _edit(request, Event, EventForm, pk, 'forms', reverse('workspace:events'),
                 'workspace/events/edit.html', 'Event')


@workspace_view('partners', 'workspace.view_benefit')
def benefits_list(request):
    from django.urls import reverse
    qs = Benefit.objects.select_related('partner')
    page, per_page = _page(request, qs)
    names = dict(membership_type_options())
    rows = [{'b': b, 'types': [names.get(c, c) for c in b.type_codes()]} for b in page.object_list]
    return render_ws(request, 'workspace/benefits/list.html', {
        'page_title': 'Partners', 'page_subtitle': 'Bonuses, discounts and offers for members',
        'page': page, 'per_page': per_page, 'page_sizes': PAGE_SIZES, 'rows': rows, 'today': timezone.localdate(),
        'add_url': reverse('workspace:benefit_add') if can(request.user, 'workspace.add_benefit') else None,
        'can_edit': can(request.user, 'workspace.change_benefit'),
    }, 'partners')


@workspace_view('partners', 'workspace.add_benefit', 'workspace.change_benefit')
def benefit_edit(request, pk=None):
    from django.urls import reverse
    return _edit(request, Benefit, BenefitForm, pk, 'partners', reverse('workspace:benefits'),
                 'workspace/benefits/edit.html', 'Benefit')
