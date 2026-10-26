import uuid

from django.db import models


class AnniversaryRegistration(models.Model):
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=30)
    email = models.EmailField()
    membership_status = models.CharField(max_length=10, choices=[('yes', 'Yes'), ('not_yet', 'Not yet')])
    event_communication = models.BooleanField(default=False)
    future_updates = models.BooleanField(default=False)
    photos_videos = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '30th anniversary registration'
        verbose_name_plural = '30th anniversary registrations'

    def __str__(self):
        return self.full_name


class ConferenceRegistration(models.Model):
    payment_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    job_title = models.CharField(max_length=255)
    organization = models.CharField('university or company name', max_length=255)
    country = models.CharField(max_length=100)
    mobile_phone = models.CharField(max_length=30)
    accepted_terms = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'TESOL conference registration'
        verbose_name_plural = 'TESOL conference registrations'

    def __str__(self):
        return self.full_name


class Membership(models.Model):

    # 1. Basic Personal Information
    full_name = models.CharField(max_length=255)
    
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
    ]
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    
    date_of_birth = models.DateField(blank=True, null=True)
    nationality = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField()

    # 2. Location
    country = models.CharField(max_length=100)
    region_city = models.CharField(max_length=100)
    address = models.TextField(blank=True, null=True)

    # 3. Professional Information
    POSITION_CHOICES = [
        ('teacher', 'Teacher'),
        ('lecturer', 'Lecturer'),
        ('student', 'Student'),
        ('leader', 'School Leader'),
        ('trainer', 'Trainer'),
        ('other', 'Other'),
    ]

    position = models.CharField(max_length=20, choices=POSITION_CHOICES)
    institution_name = models.CharField(max_length=255)

    INSTITUTION_TYPE_CHOICES = [
        ('school', 'School'),
        ('university', 'University'),
        ('training', 'Training Center'),
        ('private', 'Private'),
        ('ngo', 'NGO'),
        ('other', 'Other'),
    ]

    institution_type = models.CharField(max_length=20, choices=INSTITUTION_TYPE_CHOICES)

    EXPERIENCE_CHOICES = [
        ('0-2', '0–2'),
        ('3-5', '3–5'),
        ('6-10', '6–10'),
        ('10+', '10+'),
    ]

    experience = models.CharField(max_length=10, choices=EXPERIENCE_CHOICES)

    subjects = models.CharField(max_length=255, blank=True, null=True)
    levels = models.CharField(max_length=255, blank=True, null=True)

    # 4. Membership Type
    MEMBERSHIP_TYPE_CHOICES = [
        ('basic', 'Basic Membership'),
        ('student', 'Student / Early Career / Retired'),
        ('teacher', 'Individual Teacher'),
        ('institutional', 'Institutional Membership'),
    ]

    membership_type = models.CharField(max_length=50)

    # 5. Interests
    interests = models.TextField(blank=True, null=True, help_text="Comma separated values")

    join_sig = models.BooleanField(default=False)
    sig_areas = models.TextField(blank=True, null=True)

    # 6. Engagement
    contribution = models.TextField(blank=True, null=True, help_text="Comma separated values")
    participated_before = models.BooleanField(default=False)
    participation_details = models.TextField(blank=True, null=True)

    # 7. Communication
    LANGUAGE_CHOICES = [
        ('uz', 'Uzbek'),
        ('en', 'English'),
        ('ru', 'Russian'),
    ]

    preferred_language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES)

    CONTACT_METHOD_CHOICES = [
        ('email', 'Email'),
        ('telegram', 'Telegram'),
        ('both', 'Both'),
    ]

    contact_method = models.CharField(max_length=10, choices=CONTACT_METHOD_CHOICES)

    # 8. Institutional (conditional)
    institution_teachers_count = models.IntegerField(blank=True, null=True)
    contact_person_name = models.CharField(max_length=255, blank=True, null=True)
    contact_person_email = models.EmailField(blank=True, null=True)
    collaboration_interest = models.TextField(blank=True, null=True)

    # 8b. Institutional — members
    member_2_name = models.CharField(max_length=255, blank=True, null=True)
    member_2_email = models.EmailField(blank=True, null=True)
    member_3_name = models.CharField(max_length=255, blank=True, null=True)
    member_3_email = models.EmailField(blank=True, null=True)
    member_4_name = models.CharField(max_length=255, blank=True, null=True)
    member_4_email = models.EmailField(blank=True, null=True)
    member_5_name = models.CharField(max_length=255, blank=True, null=True)
    member_5_email = models.EmailField(blank=True, null=True)

    # 9. Payment
    PAYMENT_METHOD_CHOICES = [
        ('atmos', 'Atmos'),
        ('payme', 'Payme'),
    ]

    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='atmos')
    payment_proof = models.FileField(upload_to='payments/', blank=True, null=True)
    is_pending_payment = models.BooleanField(
        default=False,
        db_index=True,
        editable=False,
        help_text='Controls whether this application is shown in the Pending Payment admin section.',
    )

    # 10. Consent
    agree_terms = models.BooleanField(default=False)
    consent_data = models.BooleanField(default=False)
    agree_communication = models.BooleanField(default=False)

    # 11. Optional
    motivation = models.TextField(blank=True, null=True)
    challenges = models.TextField(blank=True, null=True)
    expectations = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name

    def get_membership_type_display(self):
        """Return the admin-configured name while keeping old records readable."""
        try:
            config = MembershipTypeConfig.objects.filter(
                membership_type=self.membership_type
            ).only('name').first()
            if config:
                return config.name
        except Exception:
            pass
        return dict(self.MEMBERSHIP_TYPE_CHOICES).get(
            self.membership_type,
            self.membership_type.replace('-', ' ').replace('_', ' ').title(),
        )


class PendingPayment(Membership):
    class Meta:
        proxy = True
        verbose_name = 'Pending Payment'
        verbose_name_plural = 'Pending Payments'


class MembershipTypeConfig(models.Model):
    membership_type = models.SlugField(
        max_length=50,
        unique=True,
        verbose_name='Code',
        help_text='Unique code, for example: premium or corporate-plan.',
    )
    name = models.CharField(max_length=120, verbose_name='Display name')
    is_active = models.BooleanField(default=True, verbose_name='Active')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Price (UZS)')

    class Meta:
        verbose_name = 'Membership Type'
        verbose_name_plural = 'Membership Types'
        ordering = ['name']

    def __str__(self):
        status = '✓' if self.is_active else '✗'
        return f'{status} {self.name} — {self.price:,.0f} UZS'


class Partner(models.Model):
    full_name = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    phone_number = models.CharField(max_length=50, null=True, blank=True)
    position = models.CharField(max_length=255, null=True, blank=True)
    company_name = models.CharField(max_length=255, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    source = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = 'Partner'
        verbose_name_plural = 'Partners List'
        ordering = ('full_name', 'id')

    def __str__(self):
        return self.full_name or self.email or f'Partner #{self.pk}'


class TeacherBank(models.Model):
    full_name = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    phone_number = models.CharField(max_length=50, null=True, blank=True)
    source = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = 'Teacher Bank Entry'
        verbose_name_plural = 'Teachers Bank'
        ordering = ('full_name', 'id')

    def __str__(self):
        return self.full_name or self.email or f'Teacher #{self.pk}'

