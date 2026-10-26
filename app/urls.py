from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    auth_login,
    card_preview,
    matchedexpo_email_header,
    membership_card,
    membership_create,
    membership_terms,
    privacy_policy,
    success_view,
    uztea_email_logo,
)
from . import auth_api
from .conference import conference_register, conference_success, conference_payment
from .anniversary import anniversary_register, anniversary_success

urlpatterns = [
    path('30years/', anniversary_register, name='anniversary_register'),
    path('30years/success/', anniversary_success, name='anniversary_success'),
    path('tesol/', conference_register, name='conference_register'),
    path('tesol/success/', conference_success, name='conference_success'),
    path('tesol/payment/<uuid:token>/', conference_payment, name='conference_payment'),
    path('email-assets/matchedexpo-header.png', matchedexpo_email_header, name='matchedexpo_email_header'),
    path('email-assets/uztea-logo.png', uztea_email_logo, name='uztea_email_logo'),
    path('auth/', auth_login, name='auth'),
    path('login/', auth_login, name='auth_login'),

    # ── JWT Auth API ──
    path('auth/api/register/', auth_api.register, name='auth_register'),
    path('auth/api/login/', auth_api.login, name='auth_api_login'),
    path('auth/api/token/refresh/', TokenRefreshView.as_view(), name='auth_token_refresh'),
    path('auth/api/me/', auth_api.me, name='auth_me'),
    path('auth/api/otp/send/', auth_api.otp_send, name='auth_otp_send'),
    path('auth/api/otp/verify/', auth_api.otp_verify, name='auth_otp_verify'),
    path('apply/', membership_create, name='membership_form'),
    path('success/', success_view, name='success'),
    path('card-preview/', card_preview, name='card_preview'),
    path('membership/<int:pk>/card/', membership_card, name='membership_card'),
    path('docs/membership-terms/', membership_terms, name='membership_terms'),
    path('docs/privacy-policy/', privacy_policy, name='privacy_policy'),
]
