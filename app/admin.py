import logging
from email.mime.image import MIMEImage

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db.models import Count, Q, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import escape, strip_tags
from ckeditor_uploader.widgets import CKEditorUploadingWidget
from import_export import fields, resources, widgets
from import_export.admin import ImportExportModelAdmin
from urllib.parse import urljoin

from .models import Membership, MembershipTypeConfig, Partner, PendingPayment, TeacherBank
from .views import get_uztea_email_logo_bytes
from .models import ConferenceRegistration
from .models import AnniversaryRegistration


class ConferenceRegistrationResource(resources.ModelResource):
    payment_status = fields.Field(column_name='payment_status', readonly=True)
    created_at = fields.Field(
        attribute='created_at', column_name='created_at', readonly=True,
        widget=widgets.DateTimeWidget(),
    )

    class Meta:
        model = ConferenceRegistration
        import_id_fields = ('id',)
        fields = (
            'id', 'full_name', 'email', 'job_title', 'organization',
            'country', 'mobile_phone', 'accepted_terms', 'payment_status',
            'created_at',
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = True

    def dehydrate_payment_status(self, obj):
        order = getattr(obj, 'order', None)
        return order.get_status_display() if order else 'No payment order'


@admin.register(ConferenceRegistration)
class ConferenceRegistrationAdmin(ImportExportModelAdmin):
    resource_classes = (ConferenceRegistrationResource,)
    list_display = ('full_name', 'email', 'job_title', 'organization', 'country', 'mobile_phone', 'payment_status', 'created_at')
    search_fields = ('full_name', 'email', 'organization', 'mobile_phone')
    list_filter = ('country', 'order__status', 'created_at')
    readonly_fields = ('created_at',)

    @admin.display(description='Payment status', ordering='order__status')
    def payment_status(self, obj):
        order = getattr(obj, 'order', None)
        return order.get_status_display() if order else 'No payment order'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('order')


logger = logging.getLogger(__name__)

MAX_CUSTOM_EMAIL_ATTACHMENT_SIZE = 5 * 1024 * 1024

def validate_custom_email_attachment_size(uploaded_file):
    if uploaded_file.size > MAX_CUSTOM_EMAIL_ATTACHMENT_SIZE:
        raise forms.ValidationError(
            '%(filename)s is larger than the maximum allowed size of 5 MB.',
            code='attachment_too_large',
            params={'filename': uploaded_file.name},
        )


@admin.register(MembershipTypeConfig)
class MembershipTypeConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'membership_type', 'price', 'is_active', 'toggle_link')
    list_editable = ('price', 'is_active')
    search_fields = ('name', 'membership_type')
    ordering = ('name',)

    def price_display(self, obj):
        return f'{obj.price:,.0f} UZS'
    price_display.short_description = 'Price'

    def toggle_link(self, obj):
        from django.utils.html import format_html
        from django.urls import reverse
        label = '🟢 Active' if obj.is_active else '🔴 Inactive'
        return format_html('<span>{}</span>', label)
    toggle_link.short_description = 'Status'


class MembershipAdminForm(forms.ModelForm):
    membership_type = forms.ChoiceField(label='Membership type')

    class Meta:
        model = Membership
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [
            (item.membership_type, item.name)
            for item in MembershipTypeConfig.objects.filter(is_active=True)
        ]
        current = getattr(self.instance, 'membership_type', None)
        if current and current not in dict(choices):
            choices.append((current, self.instance.get_membership_type_display()))
        if not choices:
            choices = Membership.MEMBERSHIP_TYPE_CHOICES
        self.fields['membership_type'].choices = choices


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        clean_one = super().clean
        if isinstance(data, (list, tuple)):
            return [clean_one(item, initial) for item in data]
        return [clean_one(data, initial)] if data else []


class CustomMembershipEmailForm(forms.Form):
    SENDER_CHOICES = (
        ('uztea', 'UzTEA — info@uztea.uz'),
        ('matched_expo', 'MatchedExpo — info@matchedexpo.com'),
    )
    TEMPLATE_CHOICES = (
        ('uztea_brand', 'UzTEA branded — header and footer'),
        ('uztea_simple', 'UzTEA simple — minimal header and footer'),
        ('matched_expo', 'MatchedExpo — navy and gold header and footer'),
        ('custom', 'Custom — no automatic header or footer'),
    )

    sender = forms.ChoiceField(
        choices=SENDER_CHOICES,
        initial='uztea',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    template = forms.ChoiceField(
        choices=TEMPLATE_CHOICES,
        initial='uztea_brand',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_email_template'}),
    )
    subject = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Email subject'}),
    )
    body = forms.CharField(widget=CKEditorUploadingWidget(config_name='default'))
    attachments = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={'accept': '*/*'}),
        validators=[validate_custom_email_attachment_size],
        help_text='Any file type is allowed. Maximum size: 5 MB per file.',
    )


class MembershipResource(resources.ModelResource):
    """Import/export schema for membership records."""

    class Meta:
        model = Membership
        import_id_fields = ('id',)
        fields = (
            'id', 'full_name', 'gender', 'date_of_birth', 'nationality',
            'phone_number', 'email', 'country', 'region_city', 'address',
            'position', 'institution_name', 'institution_type', 'experience',
            'subjects', 'levels', 'membership_type', 'interests', 'join_sig',
            'sig_areas', 'contribution', 'participated_before',
            'participation_details', 'preferred_language', 'contact_method',
            'institution_teachers_count', 'contact_person_name',
            'contact_person_email', 'collaboration_interest', 'member_2_name',
            'member_2_email', 'member_3_name', 'member_3_email',
            'member_4_name', 'member_4_email', 'member_5_name',
            'member_5_email', 'payment_method', 'payment_proof', 'agree_terms',
            'consent_data', 'agree_communication', 'motivation', 'challenges',
            'expectations', 'created_at',
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = True


class SkipDuplicateEmailResourceMixin:
    """Keep the first non-empty email and skip later duplicates during import."""

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        super().before_import(dataset, using_transactions, dry_run, **kwargs)
        self._import_emails = {
            email.strip().lower()
            for email in self._meta.model.objects.exclude(email__isnull=True)
            .exclude(email='')
            .values_list('email', flat=True)
            if email.strip()
        }

    def before_import_row(self, row, **kwargs):
        email = row.get('email')
        if email:
            row['email'] = str(email).strip().lower()

    def skip_row(self, instance, original, row, import_validation_errors=None):
        email = (row.get('email') or '').strip().lower()
        if email:
            if email in self._import_emails:
                return True
            self._import_emails.add(email)
        return super().skip_row(
            instance,
            original,
            row,
            import_validation_errors=import_validation_errors,
        )


class PartnerResource(SkipDuplicateEmailResourceMixin, resources.ModelResource):
    class Meta:
        model = Partner
        import_id_fields = ()
        force_init_instance = True
        fields = (
            'full_name', 'email', 'phone_number', 'position',
            'company_name', 'country', 'source',
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = True


class TeacherBankResource(SkipDuplicateEmailResourceMixin, resources.ModelResource):
    class Meta:
        model = TeacherBank
        import_id_fields = ()
        force_init_instance = True
        fields = ('full_name', 'email', 'phone_number', 'source')
        export_order = fields
        skip_unchanged = True
        report_skipped = True


class ContactEmailAdminMixin:
    actions = ('compose_custom_email',)

    @admin.action(description='Send custom email to selected contacts')
    def compose_custom_email(self, request, queryset):
        selected_ids = list(queryset.values_list('pk', flat=True))
        if not selected_ids:
            self.message_user(request, 'Select at least one contact.', level=messages.WARNING)
            return None

        request.session['custom_membership_email_ids'] = selected_ids
        request.session['custom_email_model'] = self.model._meta.label_lower
        return HttpResponseRedirect(reverse('admin:app_membership_compose_email'))


@admin.register(AnniversaryRegistration)
class AnniversaryRegistrationAdmin(
    ContactEmailAdminMixin,
    ImportExportModelAdmin
):
    list_display = (
        'full_name',
        'email',
        'phone_number',
        'membership_status',
        'event_communication',
        'future_updates',
        'photos_videos',
        'created_at'
    )

    search_fields = ('full_name', 'email', 'phone_number')

    list_filter = (
        'membership_status',
        'future_updates',
        'photos_videos',
        'created_at'
    )

    readonly_fields = ('created_at',)

    @admin.action(
        description='Send custom email to selected registrations',
        permissions=['change']
    )
    def compose_custom_email(self, request, queryset):
        return super().compose_custom_email(request, queryset)


@admin.register(Partner)
class PartnerAdmin(ContactEmailAdminMixin, ImportExportModelAdmin):
    resource_classes = (PartnerResource,)
    list_display = (
        'full_name', 'email', 'phone_number', 'position',
        'company_name', 'country', 'source',
    )
    search_fields = ('full_name', 'email', 'phone_number', 'company_name', 'country', 'source')
    list_filter = ('country', 'source')
    ordering = ('full_name', 'id')


@admin.register(TeacherBank)
class TeacherBankAdmin(ContactEmailAdminMixin, ImportExportModelAdmin):
    resource_classes = (TeacherBankResource,)
    list_display = ('full_name', 'email', 'phone_number', 'source')
    search_fields = ('full_name', 'email', 'phone_number', 'source')
    list_filter = ('source',)
    ordering = ('full_name', 'id')


@admin.register(Membership)
class MembershipAdmin(ImportExportModelAdmin):
    form = MembershipAdminForm
    resource_classes = (MembershipResource,)
    import_export_change_list_template = 'admin/app/membership/change_list.html'
    actions = ('move_to_pending_payment', 'resend_welcome_email', 'compose_custom_email')

    list_display = ('card_id', 'full_name', 'email', 'membership_type', 'position',
                    'payment_status', 'email_updates', 'created_at', 'card_link')

    list_editable = ('membership_type',)

    # agree_communication = "receives UzTEA emails"; members can switch it in My profile.
    list_filter = ('membership_type', 'position', 'preferred_language', 'agree_communication')

    search_fields = ('full_name', 'email', 'institution_name')

    readonly_fields = ('card_id', 'payment_status', 'card_link')

    def changelist_view(self, request, extra_context=None):
        from atmos.models import AtmosTransaction
        from click.models import Order

        successful_atmos_order_ids = [
            int(account)
            for account in AtmosTransaction.objects.filter(status='SUCCESS')
            .values_list('account', flat=True)
            if str(account).isdigit()
        ]
        paid_rows = (
            Order.objects.filter(
                Q(status='paid') | Q(pk__in=successful_atmos_order_ids),
                membership__isnull=False,
            )
            .values('membership__membership_type')
            .annotate(
                total=Sum('amount'),
                payment_count=Count('id'),
                promocode_count=Count('id', filter=Q(promocode__isnull=False)),
            )
            .order_by('membership__membership_type')
        )
        type_configs = list(MembershipTypeConfig.objects.all())
        type_names = {item.membership_type: item.name for item in type_configs}
        fallback_names = dict(Membership.MEMBERSHIP_TYPE_CHOICES)
        totals_by_type = {
            row['membership__membership_type']: row
            for row in paid_rows
        }
        ordered_types = [item.membership_type for item in type_configs]
        ordered_types.extend(
            membership_type
            for membership_type in totals_by_type
            if membership_type not in type_names
        )

        payment_cards = []
        for membership_type in ordered_types:
            row = totals_by_type.get(membership_type, {})
            total = row.get('total') or 0
            payment_cards.append({
                'name': type_names.get(
                    membership_type,
                    fallback_names.get(membership_type, membership_type.replace('-', ' ').title()),
                ),
                'total_display': f'{total:,.0f}'.replace(',', ' '),
                'payment_count': row.get('payment_count', 0),
                'promocode_count': row.get('promocode_count', 0),
            })

        grand_total = sum((row.get('total') or 0) for row in totals_by_type.values())
        grand_payment_count = sum(row.get('payment_count', 0) for row in totals_by_type.values())
        payment_cards.append({
            'name': 'Total Revenue',
            'total_display': f'{grand_total:,.0f}'.replace(',', ' '),
            'payment_count': grand_payment_count,
            'is_total': True,
        })

        extra_context = {
            **(extra_context or {}),
            'membership_payment_cards': payment_cards,
        }
        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_pending_payment=False)

    @staticmethod
    def _has_successful_payment(membership):
        from atmos.models import AtmosTransaction

        order_ids = list(membership.orders.values_list('id', flat=True))
        if membership.orders.filter(status='paid').exists():
            return True
        if not order_ids:
            return False
        return AtmosTransaction.objects.filter(
            account__in=[str(order_id) for order_id in order_ids],
            status='SUCCESS',
        ).exists()

    @admin.action(description='Move non-success payments to Pending Payment')
    def move_to_pending_payment(self, request, queryset):
        move_ids = []
        success_count = 0

        for membership in queryset.iterator(chunk_size=100):
            if self._has_successful_payment(membership):
                success_count += 1
            else:
                move_ids.append(membership.pk)

        moved_count = Membership.objects.filter(pk__in=move_ids).update(is_pending_payment=True)
        if moved_count:
            self.message_user(
                request,
                f'{moved_count} membership(s) moved to Pending Payment.',
                level=messages.SUCCESS,
            )
        if success_count:
            self.message_user(
                request,
                f'{success_count} successful membership(s) stayed in Memberships.',
                level=messages.INFO,
            )

    def get_urls(self):
        custom_urls = [
            path(
                'compose-email/',
                self.admin_site.admin_view(self.compose_email_view),
                name='app_membership_compose_email',
            ),
        ]
        return custom_urls + super().get_urls()

    @admin.action(description='Send custom email to selected memberships')
    def compose_custom_email(self, request, queryset):
        selected_ids = list(queryset.values_list('pk', flat=True))
        if not selected_ids:
            self.message_user(request, 'Select at least one membership.', level=messages.WARNING)
            return None

        request.session['custom_membership_email_ids'] = selected_ids
        request.session['custom_email_model'] = Membership._meta.label_lower
        return HttpResponseRedirect(reverse('admin:app_membership_compose_email'))

    def compose_email_view(self, request):
        email_models = {
            Membership._meta.label_lower: Membership,
            Partner._meta.label_lower: Partner,
            TeacherBank._meta.label_lower: TeacherBank,
            AnniversaryRegistration._meta.label_lower: AnniversaryRegistration,
        }
        model_label = request.session.get('custom_email_model', Membership._meta.label_lower)
        recipient_model = email_models.get(model_label, Membership)
        permission_name = (
            f'{recipient_model._meta.app_label}.change_{recipient_model._meta.model_name}'
        )
        if not request.user.has_perm(permission_name):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

        selected_ids = request.session.get('custom_membership_email_ids', [])
        recipients = (
            recipient_model.objects.filter(pk__in=selected_ids)
            .exclude(email__isnull=True)
            .exclude(email='')
            .order_by('full_name', 'pk')
        )
        recipient_count = recipients.count()
        changelist_url = reverse(
            f'admin:{recipient_model._meta.app_label}_{recipient_model._meta.model_name}_changelist'
        )
        recipient_label = recipient_model._meta.verbose_name_plural

        if not selected_ids:
            self.message_user(
                request,
                'Select contacts before opening the email composer.',
                level=messages.WARNING,
            )
            return HttpResponseRedirect(changelist_url)

        if request.method == 'POST':
            form = CustomMembershipEmailForm(request.POST, request.FILES)
            if form.is_valid():
                subject = form.cleaned_data['subject']
                sender = form.cleaned_data['sender']
                template_name = form.cleaned_data['template']
                content_html = self._absolute_email_urls(cleaned_html=form.cleaned_data['body'])
                attachments = [
                    (uploaded.name, uploaded.read(), uploaded.content_type)
                    for uploaded in form.cleaned_data['attachments']
                ]
                sent_count = 0
                failed_count = 0
                inline_images = []
                if template_name == 'matched_expo':
                    inline_images.append((
                        'matchedexpo-header',
                        'matchedexpo-email-header.png',
                        (settings.BASE_DIR / 'static' / 'images' / 'matchedexpo-email-header.png').read_bytes(),
                    ))
                elif template_name in ('uztea_brand', 'uztea_simple'):
                    inline_images.append((
                        'uztea-logo',
                        'uztea-logo-white.png',
                        get_uztea_email_logo_bytes(),
                    ))

                if sender == 'matched_expo':
                    connection_options = {
                        'backend': settings.MATCHED_EXPO_EMAIL_BACKEND,
                        'host': settings.MATCHED_EXPO_EMAIL_HOST,
                        'port': settings.MATCHED_EXPO_EMAIL_PORT,
                        'username': settings.MATCHED_EXPO_EMAIL_HOST_USER,
                        'password': settings.MATCHED_EXPO_EMAIL_HOST_PASSWORD,
                        'use_tls': settings.MATCHED_EXPO_EMAIL_USE_TLS,
                        'use_ssl': settings.MATCHED_EXPO_EMAIL_USE_SSL,
                        'timeout': settings.MATCHED_EXPO_EMAIL_TIMEOUT,
                    }
                    from_email = settings.MATCHED_EXPO_DEFAULT_FROM_EMAIL
                else:
                    connection_options = {}
                    from_email = settings.DEFAULT_FROM_EMAIL

                try:
                    connection = get_connection(fail_silently=False, **connection_options)
                    connection.open()
                except Exception as exc:
                    logger.exception('Custom membership email SMTP connection failed: %s', exc)
                    self.message_user(
                        request,
                        'Could not connect to the email server. Check SMTP host, port and firewall.',
                        level=messages.ERROR,
                    )
                    context = {
                        **self.admin_site.each_context(request),
                        'opts': recipient_model._meta,
                        'title': 'Compose custom email',
                        'form': form,
                        'recipients': recipients[:100],
                        'recipient_count': recipient_count,
                        'recipient_label': recipient_label,
                        'changelist_url': changelist_url,
                        'media': form.media,
                    }
                    return render(request, 'admin/app/membership/compose_email.html', context)

                try:
                    for membership in recipients.iterator(chunk_size=50):
                        try:
                            html_body = self._wrap_custom_email(
                                content_html,
                                template_name,
                                recipient_name=membership.full_name,
                            )
                            text_body = strip_tags(html_body)
                            email = EmailMultiAlternatives(
                                subject=subject,
                                body=text_body,
                                from_email=from_email,
                                to=[membership.email],
                                connection=connection,
                            )
                            if inline_images:
                                email.mixed_subtype = 'related'
                                for content_id, filename, image_content in inline_images:
                                    inline_image = MIMEImage(image_content, _subtype='png')
                                    inline_image.add_header('Content-ID', f'<{content_id}>')
                                    inline_image.add_header(
                                        'Content-Disposition',
                                        'inline',
                                        filename=filename,
                                    )
                                    email.attach(inline_image)
                            email.attach_alternative(html_body, 'text/html')
                            for filename, content, content_type in attachments:
                                email.attach(filename, content, content_type)
                            email.send(fail_silently=False)
                            sent_count += 1
                        except Exception as exc:
                            logger.exception(
                                'Custom email failed for contact #%s (%s): %s',
                                membership.pk,
                                membership.email,
                                exc,
                            )
                            failed_count += 1
                finally:
                    connection.close()

                if sent_count:
                    self.message_user(
                        request,
                        f'Custom email sent successfully to {sent_count} contact(s).',
                        level=messages.SUCCESS,
                    )
                if failed_count:
                    self.message_user(
                        request,
                        f'Custom email could not be sent to {failed_count} contact(s). Check email logs.',
                        level=messages.ERROR,
                    )
                if not failed_count:
                    request.session.pop('custom_membership_email_ids', None)
                    request.session.pop('custom_email_model', None)
                return HttpResponseRedirect(changelist_url)
        else:
            form = CustomMembershipEmailForm()

        context = {
            **self.admin_site.each_context(request),
            'opts': recipient_model._meta,
            'title': 'Compose custom email',
            'form': form,
            'recipients': recipients[:100],
            'recipient_count': recipient_count,
            'recipient_label': recipient_label,
            'changelist_url': changelist_url,
            'media': form.media,
        }
        return render(request, 'admin/app/membership/compose_email.html', context)

    @staticmethod
    def _absolute_email_urls(cleaned_html):
        base_url = getattr(settings, 'SITE_BASE_URL', 'https://uztea.uz').rstrip('/') + '/'
        return (
            cleaned_html
            .replace('src="/media/', f'src="{urljoin(base_url, "media/")}')
            .replace("src='/media/", f"src='{urljoin(base_url, 'media/')}")
            .replace('href="/media/', f'href="{urljoin(base_url, "media/")}')
            .replace("href='/media/", f"href='{urljoin(base_url, 'media/')}")
        )

    @staticmethod
    def _wrap_custom_email(content_html, template_name, recipient_name=''):
        if template_name == 'custom':
            return content_html

        if template_name == 'matched_expo':
            safe_recipient_name = escape(recipient_name or 'Member')
            return (
                '<!doctype html><html><head>'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<meta name="color-scheme" content="light only">'
                '<meta name="supported-color-schemes" content="light only">'
                '<style>:root{color-scheme:light only!important;supported-color-schemes:light only!important}'
                '@media only screen and (max-width:600px){'
                '.mx-outer{padding:0!important}.mx-shell{width:100%!important;max-width:100%!important}'
                '.mx-greeting{padding:24px 18px 8px!important}.mx-content{padding:20px 22px 30px!important}'
                '.mx-footer{padding:24px 16px!important}'
                '}</style></head><body style="margin:0;padding:0;background:#edf1f6;color:#26364c;'
                '-webkit-text-size-adjust:100%;text-size-adjust:100%;">'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                'class="mx-outer" bgcolor="#edf1f6" style="background:#edf1f6;padding:30px 12px;"><tr><td align="center">'
                '<table role="presentation" width="640" cellpadding="0" cellspacing="0" class="mx-shell" bgcolor="#ffffff" '
                'style="width:100%;max-width:640px;background:#ffffff;border-collapse:collapse;">'
                '<tr><td bgcolor="#001b3d" style="background:#001b3d;line-height:0;font-size:0;">'
                '<img src="cid:matchedexpo-header" width="640" alt="MatchED Expo Uzbekistan" '
                'style="display:block;width:100%;max-width:640px;height:auto;border:0;"></td></tr>'
                '<tr><td class="mx-greeting" bgcolor="#ffffff" style="background:#ffffff;padding:34px 42px 8px;text-align:center;font-family:Arial,sans-serif;">'
                f'<div style="font-size:21px;font-weight:700;color:#001b3d;">Dear {safe_recipient_name},</div>'
                '<div style="width:48px;height:3px;margin:12px auto 0;background:#d4a442;font-size:0;">&nbsp;</div>'
                '</td></tr>'
                '<tr><td class="mx-content" bgcolor="#ffffff" style="background:#ffffff;padding:24px 42px 38px;font-family:Arial,sans-serif;font-size:15px;'
                f'line-height:1.7;color:#26364c;">{content_html}</td></tr>'
                '<tr><td style="height:4px;background:#d4a442;font-size:0;line-height:0;">&nbsp;</td></tr>'
                '<tr><td class="mx-footer" align="center" bgcolor="#001b3d" '
                'style="background:#001b3d;padding:28px 20px 24px;color:#ffffff;text-align:center;font-family:Arial,sans-serif;">'
                '<div style="font-size:17px;font-weight:700;line-height:1.35;color:#ffffff;">'
                'Stay connected with MatchED Expo</div>'
                '<div style="margin-top:8px;font-size:10px;line-height:1.5;color:#d9e2ef;">'
                'Education, institutions, opportunities and exhibition updates</div>'
                '<table role="presentation" align="center" cellpadding="0" cellspacing="0" style="margin:16px auto 12px;">'
                '<tr>'
                '<td style="padding:0 5px;"><a href="https://t.me/matchedexpo" '
                'style="display:block;width:32px;height:32px;border-radius:50%;background:#2678c9;color:#fff;'
                'font-size:9px;font-weight:700;line-height:32px;text-align:center;text-decoration:none;">TG</a></td>'
                '<td style="padding:0 5px;"><a href="https://www.instagram.com/matchedexpo/" '
                'style="display:block;width:32px;height:32px;border-radius:50%;background:#2678c9;color:#fff;'
                'font-size:9px;font-weight:700;line-height:32px;text-align:center;text-decoration:none;">IG</a></td>'
                '<td style="padding:0 5px;"><a href="https://www.youtube.com/@MatchEDExpo" '
                'style="display:block;width:32px;height:32px;border-radius:50%;background:#2678c9;color:#fff;'
                'font-size:9px;font-weight:700;line-height:32px;text-align:center;text-decoration:none;">YT</a></td>'
                '<td style="padding:0 5px;"><a href="https://www.linkedin.com/showcase/matched-expo-uzbekistan/" '
                'style="display:block;width:32px;height:32px;border-radius:50%;background:#2678c9;color:#fff;'
                'font-size:9px;font-weight:700;line-height:32px;text-align:center;text-decoration:none;">IN</a></td>'
                '<td style="padding:0 5px;"><a href="https://www.facebook.com/profile.php?id=61581164442313" '
                'style="display:block;width:32px;height:32px;border-radius:50%;background:#2678c9;color:#fff;'
                'font-size:9px;font-weight:700;line-height:32px;text-align:center;text-decoration:none;">FB</a></td>'
                '</tr></table>'
                '<div style="font-size:10px;line-height:1.8;color:#ffffff;">'
                '<a href="mailto:info@matchedexpo.com" style="color:#fff;text-decoration:none;white-space:nowrap;">'
                'info@matchedexpo.com</a><span style="color:#8ca3bf;"> &nbsp;|&nbsp; </span>'
                '<a href="https://www.matchedexpo.com" style="color:#fff;text-decoration:none;white-space:nowrap;">'
                'www.matchedexpo.com</a></div>'
                '</td></tr>'
                '<tr><td style="height:7px;background:#c99a3d;font-size:0;line-height:0;">&nbsp;</td></tr>'
                '</table></td></tr></table></body></html>'
            )

        safe_recipient_name = escape(recipient_name or 'Member')
        compact = template_name == 'uztea_simple'
        header_padding = '13px 24px' if compact else '28px 34px'
        logo_width = '82' if compact else '112'
        association_width = '115' if compact else '145'
        header = (
            '<tr><td style="height:5px;background:#f5b706;font-size:0;line-height:0;">&nbsp;</td></tr>'
            f'<tr><td style="background:#001f4d;padding:{header_padding};">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td width="{logo_width}" valign="middle" style="padding-right:18px;">'
            f'<img src="cid:uztea-logo" width="{logo_width}" alt="UzTEA" '
            f'style="display:block;width:{logo_width}px;max-width:100%;height:auto;border:0;">'
            f'</td><td width="{association_width}" valign="middle" style="padding:0 22px;border-right:1px solid #7890ae;'
            'font-family:Arial,sans-serif;font-size:11px;line-height:1.55;color:#ffffff;">'
            'Uzbekistan<br>Teachers of English<br>Association'
            '</td><td valign="middle" style="padding-left:28px;font-family:Arial,sans-serif;color:#ffffff;">'
            '<div style="font-size:18px;font-weight:700;line-height:1.35;">Connecting English language educators</div>'
            '<div style="font-size:12px;line-height:1.5;margin-top:5px;color:#d9e2ef;">'
            'Inspiring professional growth across Uzbekistan</div>'
            '</td></tr></table></td></tr>'
        )
        greeting_and_message = (
            '<tr><td style="padding:30px 40px 12px;text-align:center;font-family:Arial,sans-serif;">'
            f'<div style="font-size:20px;font-weight:700;color:#001f4d;">Dear {safe_recipient_name},</div>'
            '<div style="width:48px;height:3px;margin:11px auto 0;background:#d4a442;font-size:0;">&nbsp;</div>'
            '</td></tr>'
            '<tr><td style="padding:16px 40px 36px;font-family:Arial,sans-serif;">'
            '<div style="background:#f4f5f7;padding:30px;font-size:14px;line-height:1.7;color:#1e3353;">'
            f'{content_html}</div></td></tr>'
        )
        if compact:
            footer = (
                '<tr><td style="height:3px;background:#f5b706;font-size:0;line-height:0;">&nbsp;</td></tr>'
                '<tr><td style="background:#001f4d;padding:16px 24px;text-align:center;'
                'font-family:Arial,sans-serif;color:#ffffff;">'
                '<div style="font-size:13px;font-weight:700;">Stay connected with UzTEA</div>'
                '<div style="margin-top:7px;font-size:10px;line-height:1.7;">'
                '<a href="mailto:info@uztea.uz" style="color:#fff;text-decoration:none;">info@uztea.uz</a>'
                ' &nbsp; | &nbsp; <a href="https://uztea.uz" style="color:#fff;text-decoration:none;">www.uztea.uz</a>'
                '</div></td></tr>'
            )
        else:
            footer = (
            '<tr><td style="background:#001f4d;padding:28px 26px 24px;text-align:center;'
            'font-family:Arial,sans-serif;color:#ffffff;">'
            '<div style="font-size:18px;font-weight:700;">Stay connected with UzTEA</div>'
            '<div style="margin-top:8px;font-size:11px;color:#d9e2ef;">'
            'News, events, professional opportunities and community updates</div>'
            '<div style="margin-top:18px;font-size:12px;line-height:2.2;">'
            '<a href="https://t.me/uzteauz" style="display:inline-block;margin:0 5px;padding:4px 10px;'
            'background:#1457aa;color:#fff;text-decoration:none;border-radius:18px;">Telegram</a>'
            '<a href="https://www.instagram.com/uztea.uz" style="display:inline-block;margin:0 5px;padding:4px 10px;'
            'background:#1457aa;color:#fff;text-decoration:none;border-radius:18px;">Instagram</a>'
            '<a href="https://www.youtube.com/@UzTEA" style="display:inline-block;margin:0 5px;padding:4px 10px;'
            'background:#1457aa;color:#fff;text-decoration:none;border-radius:18px;">YouTube</a>'
            '<a href="https://www.linkedin.com/company/uztea" style="display:inline-block;margin:0 5px;padding:4px 10px;'
            'background:#1457aa;color:#fff;text-decoration:none;border-radius:18px;">LinkedIn</a>'
            '<a href="https://www.facebook.com/uztea" style="display:inline-block;margin:0 5px;padding:4px 10px;'
            'background:#1457aa;color:#fff;text-decoration:none;border-radius:18px;">Facebook</a>'
            '</div><div style="margin-top:15px;font-size:12px;">'
            '<a href="mailto:info@uztea.uz" style="color:#fff;text-decoration:none;">info@uztea.uz</a>'
            ' &nbsp; | &nbsp; <a href="https://uztea.uz" style="color:#fff;text-decoration:none;">www.uztea.uz</a>'
            '</div></td></tr>'
            '<tr><td style="height:5px;background:#f5b706;font-size:0;line-height:0;">&nbsp;</td></tr>'
            )

        return (
            '<!doctype html><html><body style="margin:0;padding:0;background:#eef2f8;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="background:#eef2f8;padding:30px 12px;"><tr><td align="center">'
            '<table role="presentation" width="640" cellpadding="0" cellspacing="0" '
            'style="width:100%;max-width:640px;background:#ffffff;border-collapse:collapse;">'
            f'{header}{greeting_and_message}{footer}'
            '</table></td></tr></table></body></html>'
        )


    @admin.action(description='Resend welcome email to selected memberships')
    def resend_welcome_email(self, request, queryset):
        from datetime import timedelta

        from atmos.email import send_welcome_email

        sent_count = 0
        failed_count = 0
        skipped_count = 0
        expiry_date = (timezone.now() + timedelta(days=365)).strftime('%d %B %Y')

        for membership in queryset.iterator(chunk_size=50):
            if not membership.email:
                skipped_count += 1
                continue

            sent = send_welcome_email(
                email=membership.email,
                full_name=membership.full_name,
                membership_id=f'UZ{membership.id:06d}',
                membership_type=membership.get_membership_type_display(),
                expiry_date=expiry_date,
            )
            if sent:
                sent_count += 1
            else:
                failed_count += 1

        if sent_count:
            self.message_user(
                request,
                f'Welcome email resent successfully to {sent_count} member(s).',
                level=messages.SUCCESS,
            )
        if failed_count:
            self.message_user(
                request,
                f'Welcome email could not be sent to {failed_count} member(s). Check email logs.',
                level=messages.ERROR,
            )
        if skipped_count:
            self.message_user(
                request,
                f'{skipped_count} member(s) skipped because no email address was provided.',
                level=messages.WARNING,
            )

    @admin.display(boolean=True, description='Email updates', ordering='agree_communication')
    def email_updates(self, obj):
        # Members switch this in My profile (the application's "agree to receive communications").
        return obj.agree_communication

    def card_id(self, obj):
        return f'UZ{obj.id:06d}' if obj.id else '—'
    card_id.short_description = 'Membership ID'

    def payment_status(self, obj):
        from django.utils.html import format_html
        from .payment_status import membership_payment_status, payment_status_style

        if not obj.id:
            return format_html(
                '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
                'background:#f1f5f9;color:#64748b;font-size:11px;font-weight:700;">—</span>'
            )

        # Latest Atmos transaction wins, otherwise the latest order status
        bg, fg, label = payment_status_style(membership_payment_status(obj))

        return format_html(
            '<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
            'background:{};color:{};font-size:11px;font-weight:700;">{}</span>',
            bg, fg, label
        )
    payment_status.short_description = 'Status'

    def card_link(self, obj):
        from django.utils.html import format_html
        from django.urls import reverse
        if not obj.id:
            return '—'
        url = reverse('membership_card', args=[obj.id]) + '?download=1'
        return format_html(
            '<a href="{}" '
            'style="display:inline-block;padding:4px 12px;background:#222e50;color:#fff;'
            'border-radius:6px;text-decoration:none;font-weight:600;font-size:12px;">'
            '⬇ Download</a>', url
        )
    card_link.short_description = 'Membership Card'

    fieldsets = (
        ('👤 Personal Info', {
            'fields': ('full_name', 'gender', 'date_of_birth', 'nationality', 'phone_number', 'email')
        }),

        ('📍 Location', {
            'fields': ('country', 'region_city', 'address')
        }),

        ('💼 Professional Info', {
            'fields': ('position', 'institution_name', 'institution_type', 'experience', 'subjects', 'levels')
        }),

        ('🎓 Membership', {
            'fields': ('membership_type',)
        }),

        ('🤝 Engagement', {
            'fields': ('contribution', 'participated_before', 'participation_details')
        }),

        ('📢 Communication', {
            'fields': ('preferred_language', 'contact_method')
        }),

        ('🏫 Institutional Members', {
            'fields': ('member_2_name', 'member_2_email', 'member_3_name', 'member_3_email',
                       'member_4_name', 'member_4_email', 'member_5_name', 'member_5_email')
        }),

        ('✅ Consent', {
            'fields': ('agree_terms', 'consent_data', 'agree_communication')
        }),

        ('💡 Optional', {
            'fields': ('motivation', 'challenges', 'expectations')
        }),
    )


@admin.register(PendingPayment)
class PendingPaymentAdmin(MembershipAdmin):
    actions = ('compose_custom_email', 'return_to_memberships')
    import_export_change_list_template = 'admin/import_export/change_list_import_export.html'

    def get_urls(self):
        # The email composer belongs to the Membership admin only.
        return ImportExportModelAdmin.get_urls(self)

    def get_queryset(self, request):
        return ImportExportModelAdmin.get_queryset(self, request).filter(is_pending_payment=True)

    @admin.action(description='Return selected records to Memberships')
    def return_to_memberships(self, request, queryset):
        restored_count = Membership.objects.filter(
            pk__in=queryset.values_list('pk', flat=True)
        ).update(is_pending_payment=False)
        self.message_user(
            request,
            f'{restored_count} membership(s) returned to Memberships.',
            level=messages.SUCCESS,
        )
