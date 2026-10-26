from django.urls import path
from . import views

urlpatterns = [
    # Frontend sahifasi
    path('pay/', views.payment_page, name='atmos-payment-page'),

    # UzCard / Humo API
    path('api/start/',     views.start_payment,  name='atmos-start'),
    path('api/retry-otp/', views.retry_otp,       name='atmos-retry-otp'),
    path('api/confirm/',   views.confirm_payment, name='atmos-confirm'),
    path('api/callback/',  views.payment_callback, name='atmos-callback'),

    # MPS (Visa / Mastercard) API
    path('mps/api/start/', views.mps_start, name='atmos-mps-start'),
    path('mps/api/apply/', views.mps_apply, name='atmos-mps-apply'),

    path('api/<str:transaction_id>/', views.transaction_detail, name='atmos-detail'),
]
