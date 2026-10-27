import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_list(name, default=None):
    value = os.getenv(name)
    if not value:
        return default or []
    return [item.strip() for item in value.split(',') if item.strip()]

SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = _env_bool('DEBUG', False)

ALLOWED_HOSTS = _env_list('ALLOWED_HOSTS', ['*', 'easiness-wrath-swiftness.ngrok-free.dev'])
CSRF_TRUSTED_ORIGINS = _env_list('CSRF_TRUSTED_ORIGINS')


MY_APPS = [
    'app',
    'click',
    'atmos',
    'payme',
    'workspace',
    'certificates',
]

THIRD_PARTY_APPS = [
    'ckeditor',
    'ckeditor_uploader',
    'drf_yasg',
    'rest_framework',
    'import_export',
    'corsheaders',
    "drf_spectacular",
]

INSTALLED_APPS = [
                     'jazzmin',
                     'django.contrib.admin',
                     'django.contrib.auth',
                     'django.contrib.contenttypes',
                     'django.contrib.sessions',
                     'django.contrib.messages',
                     'django.contrib.staticfiles',
                 ] + MY_APPS + THIRD_PARTY_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # certificates.uztea.uz -> /certificates/ (certificate portal)
    'certificates.middleware.CertificatesHostMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    # 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'root.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates']
        ,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'root.wsgi.application'

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

POSTGRES_DB = os.getenv('POSTGRES_DB')
if POSTGRES_DB:
    DATABASES = {
        'default': {
            'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.postgresql_psycopg2'),
            'NAME': POSTGRES_DB,
            'USER': os.getenv('POSTGRES_USER'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
            'HOST': os.getenv('POSTGRES_HOST', '127.0.0.1'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
        }
    }

# AUTH_PASSWORD_VALIDATORS = [
#     {
#         'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
#     },
#     {
#         'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
#     },
#     {
#         'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
#     },
#     {
#         'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
#     },
# ]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Tashkent'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = os.path.join(BASE_DIR / 'staticfiles')

MEDIA_URL = 'media/'
MEDIA_ROOT = os.path.join(BASE_DIR / 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Swagger Config

SWAGGER_SETTINGS = {
    'VALIDATOR_URL': 'http://localhost:8189',
    'DEFAULT_INFO': 'import.path.to.urls.api_info',
    'USE_SESSION_AUTH': True,
    'SECURITY_DEFINITIONS': {
        'basic': {
            'type': 'basic'
        },
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'Type in the *\'Value\'* input box below: **\'Bearer &lt;JWT&gt;\'**, '
                           'where JWT is the JSON web token you get back when logging in.'
        }
    }

}

# CORS Config
CORS_ALLOW_ALL_ORIGINS = True

CORS_ALLOWED_ORIGINS = [
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",

]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication'
    ),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend'
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# If you have a custom user model in a `users` app, re-enable this line.
# AUTH_USER_MODEL = 'users.User'


SPECTACULAR_SETTINGS = {
    "TITLE": "UzTea API",
    "VERSION": "1.0.0",
}



# JWT Config




SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60, days=100),
    "REFRESH_TOKEN_LIFETIME": timedelta(minutes=60, days=100),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": False,

    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.getenv('SECRET_KEY'),
    "VERIFYING_KEY": "",
    "AUDIENCE": None,
    "ISSUER": None,
    "JSON_ENCODER": None,
    "JWK_URL": None,
    "LEEWAY": 0,

    "AUTH_HEADER_TYPES": ('Bearer',),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication.default_user_authentication_rule",

    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",

    "JTI_CLAIM": "jti",

    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "SLIDING_TOKEN_LIFETIME": timedelta(minutes=10),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(days=1),

    "TOKEN_OBTAIN_SERIALIZER": "rest_framework_simplejwt.serializers.TokenObtainPairSerializer",
    "TOKEN_REFRESH_SERIALIZER": "rest_framework_simplejwt.serializers.TokenRefreshSerializer",
    "TOKEN_VERIFY_SERIALIZER": "rest_framework_simplejwt.serializers.TokenVerifySerializer",
    "TOKEN_BLACKLIST_SERIALIZER": "rest_framework_simplejwt.serializers.TokenBlacklistSerializer",
    "SLIDING_TOKEN_OBTAIN_SERIALIZER": "rest_framework_simplejwt.serializers.TokenObtainSlidingSerializer",
    "SLIDING_TOKEN_REFRESH_SERIALIZER": "rest_framework_simplejwt.serializers.TokenRefreshSlidingSerializer",
}

# Email Config

EMAIL_BACKEND = os.getenv('EMAIL_BACKEND') or 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = int(os.getenv('EMAIL_PORT') or 587)
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = _env_bool('EMAIL_USE_TLS', False)
EMAIL_USE_SSL = _env_bool('EMAIL_USE_SSL', False)
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT') or 15)
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'UzTEA <info@uztea.uz>')

# Brevo (approved 2026-10-27): when BREVO_SMTP_KEY is set, all UzTEA email goes through
# Brevo's SMTP relay. The sender address must be verified in Brevo.
BREVO_SMTP_LOGIN = os.getenv('BREVO_SMTP_LOGIN', '')
BREVO_SMTP_KEY = os.getenv('BREVO_SMTP_KEY', '')
if BREVO_SMTP_LOGIN and BREVO_SMTP_KEY:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.getenv('BREVO_SMTP_HOST', 'smtp-relay.brevo.com')
    EMAIL_PORT = int(os.getenv('BREVO_SMTP_PORT') or 587)
    EMAIL_HOST_USER = BREVO_SMTP_LOGIN
    EMAIL_HOST_PASSWORD = BREVO_SMTP_KEY
    EMAIL_USE_TLS, EMAIL_USE_SSL = True, False

# Separate SMTP account used when an admin selects MatchedExpo in the custom
# membership email composer.
MATCHED_EXPO_EMAIL_BACKEND = os.getenv('MATCHED_EXPO_EMAIL_BACKEND', EMAIL_BACKEND)
MATCHED_EXPO_EMAIL_HOST = os.getenv('MATCHED_EXPO_EMAIL_HOST', '')
MATCHED_EXPO_EMAIL_PORT = int(os.getenv('MATCHED_EXPO_EMAIL_PORT') or 587)
MATCHED_EXPO_EMAIL_HOST_USER = os.getenv('MATCHED_EXPO_EMAIL_HOST_USER', '')
MATCHED_EXPO_EMAIL_HOST_PASSWORD = os.getenv('MATCHED_EXPO_EMAIL_HOST_PASSWORD', '')
MATCHED_EXPO_EMAIL_USE_TLS = _env_bool('MATCHED_EXPO_EMAIL_USE_TLS', True)
MATCHED_EXPO_EMAIL_USE_SSL = _env_bool('MATCHED_EXPO_EMAIL_USE_SSL', False)
MATCHED_EXPO_EMAIL_TIMEOUT = int(os.getenv('MATCHED_EXPO_EMAIL_TIMEOUT') or 15)
MATCHED_EXPO_DEFAULT_FROM_EMAIL = os.getenv(
    'MATCHED_EXPO_DEFAULT_FROM_EMAIL',
    'MatchedExpo <info@matchedexpo.com>',
)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_ADMIN_CHAT_ID = os.getenv('TELEGRAM_ADMIN_CHAT_ID', '')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

CKEDITOR_CONFIGS = {
    'default': {
        'toolbar': 'full',
        'height': 300,
        'width': 'auto',
        'extraPlugins': ','.join(['uploadimage']),
    },
}

CKEDITOR_UPLOAD_PATH = 'email-editor/'
CKEDITOR_RESTRICT_BY_USER = True

JAZZMIN_SETTINGS = {
    # title of the window (Will default to current_admin_site.site_title if absent or None)
    "site_title": "UzTEA Admin",

    # Title on the login screen (19 chars max) (defaults to current_admin_site.site_header if absent or None)
    "site_header": "UzTEA Admin",

    # Title on the brand (19 chars max) (defaults to current_admin_site.site_header if absent or None)
    "site_brand": "UzTEA",

    # Logo to use for your site, must be present in static files, used for brand on top left
    "site_logo": "images/logo.png",
    # "login_logo": "apps/logo/project-manager.png",
    # "login_logo_dark": 'apps/logo/project-manager.png',
    # "site_logo_classes": "img-circle",

    # Relative path to a favicon for your site, will default to site_logo if absent (ideally 32x32 px)
    "site_icon": "images/logo.png",

    # Welcome text on the login screen
    "welcome_sign": "Welcome to UzTEA Admin",

    # Copyright on the footer
    "copyright": None,

    # List of model admins to search from the search bar, search bar omitted if excluded
    # If you want to use a single search field you dont need to use a list, you can use a simple string
    "search_model": ["auth.User", "auth.Group"],

    # Field name on user model that contains avatar ImageField/URLField/Charfield or a callable that receives the user
    "user_avatar": False,

    # "custom_css": "custom_styles.css",

    ############
    # Top Menu #
    ############

    # Links to put along the top menu
    "topmenu_links": [

        # Url that gets reversed (Permissions can be added)
        {"name": "Dashboard", "url": "admin:index"},

        # external url that opens in a new window (Permissions can be added)
        {"name": "View website", "url": "https://uztea.uz/", "new_window": True},
    ],

    #############
    # User Menu #
    #############

    # Additional links to include in the user menu on the top right ("app" url type is not allowed)
    "usermenu_links": [
        {"name": "View website", "url": "https://uztea.uz/", "new_window": True},
        {"model": "auth.user"},

    ],

    #############
    # Side Menu #
    #############

    # Whether to display the side menu
    "show_sidebar": True,

    # Whether to aut expand the menu
    "navigation_expanded": True,

    # Hide these apps when generating side menu e.g (auth)
    "hide_apps": [],

    # Hide these models when generating side menu (e.g auth.user)
    "hide_models": [],

    # List of apps (and/or models) to base side menu ordering off of (does not need to contain all apps/models)
    "order_with_respect_to": ["app", "click", "atmos", "payme", "auth"],

    # Custom links to append to app groups, keyed on app name
    "custom_links": {
        "click": [{
            "name": "Click Tools & Logs",
            "url": "admin:click_order_tools",
            "icon": "fas fa-wave-square",
            "permissions": ["click.view_order"]
        }],
        "books": [{
            "name": "Make Messages",
            "url": "make_messages",
            "icon": "fas fa-comments",
            "permissions": ["books.view_book"]
        }]
    },

    # for the full list of 5.13.0 free icon classes
    "icons": {
        "app": "fas fa-id-card",
        "app.membership": "fas fa-address-card",
        "app.membershiptypeconfig": "fas fa-tags",
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "click": "fas fa-credit-card",
        "click.order": "fas fa-money-check-alt",
        "atmos": "fas fa-wallet",
        "payme": "fas fa-receipt",
    },
    # Icons that are used when one is not manually specified
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",

    #################
    # Related Modal #
    #################
    # Use modals instead of popups
    "related_modal_active": False,

    #############
    # UI Tweaks #
    #############
    # Relative paths to custom CSS/JS scripts (must be present in static files)
    "custom_css": "uztea_admin_v20.css",
    # "custom_css": '/custom_styles.css',
    "custom_js": "uztea_admin.js",
    # Whether to link font from fonts.googleapis.com (use custom_css to supply font otherwise)
    "use_google_fonts_cdn": True,
    # Whether to show the UI customizer on the sidebar
    "show_ui_builder": False,

    ###############
    # Change view #
    ###############
    # Render out the change view as a single form, or in tabs, current options are
    # - single
    # - horizontal_tabs (default)
    # - vertical_tabs
    # - collapsible
    # - carousel
    "changeform_format": "single",
    # override change forms on a per modeladmin basis
    "changeform_format_overrides": {"auth.user": "collapsible", "auth.group": "vertical_tabs"},
    # Add a language dropdown into the admin
    "language_chooser": False,

}
JAZZMIN_UI_TWEAKS = {
    "theme": "flatly",
    "navbar": "navbar-white navbar-light",
    "accent": "accent-primary",
    "sidebar": "sidebar-dark-primary",
    "brand_colour": "navbar-white",
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'click_payments.log'),
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    # Root logger — catches everything, prints full tracebacks to console + file
    'root': {
        'handlers': ['console', 'file'],
        'level': 'WARNING',
    },
    'loggers': {
        'click': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'atmos': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        # Captures full tracebacks of ANY unhandled 500 in views
        'django.request': {
            'handlers': ['file', 'console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# ── PAYME To'lov Tizimi ──────────────────────────────────────────────
PAYME_ENV        = os.getenv('PAYME_ENV', 'test')
PAYME_CASHBOX_ID = os.getenv('PAYME_CASHBOX_ID', '')
PAYME_SECRET_KEY = os.getenv('PAYME_SECRET_KEY', '')
PAYME_URL        = os.getenv('PAYME_PROD_URL') if PAYME_ENV == 'prod' else os.getenv('PAYME_TEST_URL', 'https://checkout.test.paycom.uz')

# ── ATMOS To'lov Tizimi ──────────────────────────────────────────────
SITE_BASE_URL        = os.getenv('SITE_BASE_URL', 'http://127.0.0.1:8000')
ATMOS_BASE_URL       = os.getenv('ATMOS_BASE_URL', 'https://apigw.atmos.uz')
ATMOS_CONSUMER_KEY   = os.getenv('ATMOS_CONSUMER_KEY', '')
ATMOS_CONSUMER_SECRET = os.getenv('ATMOS_CONSUMER_SECRET', '')
ATMOS_STORE_ID       = os.getenv('ATMOS_STORE_ID', '')
ATMOS_TERMINAL_ID    = os.getenv('ATMOS_TERMINAL_ID', '')
