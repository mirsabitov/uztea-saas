"""Form Studio preview content. Nothing here is stored: the studio is a sandbox
until the Form / Submission models are designed in their own phase."""

FIELD_LIBRARY = [
    ('short_text', 'Short text', 'type'),
    ('long_text', 'Long text', 'align-left'),
    ('email', 'Email', 'mail'),
    ('phone', 'Phone', 'phone'),
    ('dropdown', 'Dropdown', 'chevron-down-circle'),
    ('multiple_choice', 'Multiple choice', 'circle-dot'),
    ('checkbox', 'Checkbox', 'check-square'),
    ('date', 'Date', 'calendar'),
    ('file_upload', 'File upload', 'upload'),
]

SMART_BLOCKS = [
    ('membership_lookup', 'Membership lookup', 'users'),
    ('payment', 'Payment', 'credit-card'),
    ('consent', 'Consent', 'shield'),
]

TEMPLATES = [
    {
        'key': 'event', 'title': 'Event registration', 'icon': 'calendar',
        'form_title': 'Teacher workshop registration',
        'hero_title': 'Teaching with confidence',
        'hero_text': 'Register for our next professional learning workshop.',
        'fields': [
            {'type': 'short_text', 'label': 'Full name', 'required': True, 'placeholder': 'Enter your full name'},
            {'type': 'email', 'label': 'Email', 'required': True, 'placeholder': 'you@example.org'},
            {'type': 'multiple_choice', 'label': 'Are you an UzTEA member?', 'choices': ['Yes', 'Not yet']},
            {'type': 'dropdown', 'label': 'Session preference', 'choices': ['Morning session', 'Afternoon session'],
             'logic': 'Show membership ID when member = Yes'},
        ],
        'submit': 'Register',
    },
    {
        'key': 'membership', 'title': 'Membership application', 'icon': 'id-card',
        'form_title': 'Membership application',
        'hero_title': 'Join UzTEA',
        'hero_text': 'Become part of the Uzbekistan Teachers of English Association.',
        'fields': [
            {'type': 'short_text', 'label': 'Full name', 'required': True, 'placeholder': 'Enter your full name'},
            {'type': 'email', 'label': 'Email', 'required': True, 'placeholder': 'you@example.org'},
            {'type': 'phone', 'label': 'Phone number', 'required': True, 'placeholder': '+998'},
            {'type': 'dropdown', 'label': 'Membership type', 'choices': ['Basic', 'Student', 'Individual teacher', 'Institutional']},
            {'type': 'checkbox', 'label': 'I agree to the membership terms', 'required': True},
        ],
        'submit': 'Continue to payment',
    },
    {
        'key': 'feedback', 'title': 'Feedback survey', 'icon': 'message-square',
        'form_title': 'Community feedback',
        'hero_title': 'Tell us what you think',
        'hero_text': 'Help us plan topics and events that matter to you.',
        'fields': [
            {'type': 'multiple_choice', 'label': 'How useful was the event?', 'choices': ['Very useful', 'Useful', 'Not useful']},
            {'type': 'long_text', 'label': 'Which topics should we cover next?', 'placeholder': 'Your ideas'},
        ],
        'submit': 'Send feedback',
    },
    {
        'key': 'blank', 'title': 'Blank form', 'icon': 'file',
        'form_title': 'Untitled form', 'hero_title': 'Untitled form', 'hero_text': 'Add a short description.',
        'fields': [], 'submit': 'Submit',
    },
]
