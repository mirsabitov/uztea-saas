import base64
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from .views import PaymeMerchantAPIView


class PaymeAuthenticationTests(SimpleTestCase):
    def authenticated(self, username='Paycom', password='test-secret'):
        token = base64.b64encode(f'{username}:{password}'.encode()).decode()
        request = RequestFactory().post('/', HTTP_AUTHORIZATION=f'Basic {token}')
        return PaymeMerchantAPIView()._check_auth(request)

    @patch('payme.views.PaymeConfig.get_secret_key', return_value='test-secret')
    def test_accepts_paycom_login_seen_in_production(self, secret):
        self.assertTrue(self.authenticated())

    @patch('payme.views.PaymeConfig.get_secret_key', return_value='test-secret')
    def test_rejects_incorrect_password_and_login(self, secret):
        self.assertFalse(self.authenticated(password='wrong'))
        self.assertFalse(self.authenticated(username='Payme'))

    @patch('payme.views.PaymeConfig.get_secret_key', return_value='')
    def test_empty_secret_cannot_authenticate(self, secret):
        self.assertFalse(self.authenticated(password=''))

    def test_missing_or_malformed_header_is_rejected(self):
        for header in ('', 'Basic !!!', 'Bearer test-secret'):
            request = RequestFactory().post('/', HTTP_AUTHORIZATION=header)
            self.assertFalse(PaymeMerchantAPIView()._check_auth(request))
