from django.urls import path
from .views import PaymeMerchantAPIView

urlpatterns = [
    path('webhook/', PaymeMerchantAPIView.as_view(), name='payme_webhook'),
]
