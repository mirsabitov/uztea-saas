from django.urls import path
from .views import click_webhook, membership_payment, payment_status, team_member_card, apply_promocode

urlpatterns = [
    path('webhook/', click_webhook, name='click_webhook'),
    path('promo/apply/', apply_promocode, name='apply_promocode'),
    path('pay/<int:order_pk>/', membership_payment, name='membership_payment'),
    path('status/<int:order_pk>/', payment_status, name='payment_status'),
    path('status/<int:order_pk>/member/<int:idx>/', team_member_card, name='team_member_card'),
]
