import re
from rest_framework import serializers
from .models import AtmosTransaction
from click.models import Order


class StartPaymentSerializer(serializers.Serializer):
    amount      = serializers.IntegerField(min_value=100, help_text='Tiyinlarda')
    account     = serializers.CharField(max_length=255)
    card_number = serializers.CharField(min_length=16, max_length=19)
    expiry      = serializers.CharField(min_length=4, max_length=5)

    def validate_account(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('Account must contain digits only.')
        if Order.objects.filter(pk=value, conference_registration__isnull=False).exists():
            raise serializers.ValidationError('Please use Payme for TESOL conference payments.')
        return value

    def validate_card_number(self, value):
        digits = re.sub(r'\D', '', value)
        if len(digits) != 16:
            raise serializers.ValidationError('Card number must be exactly 16 digits.')
        return digits

    def validate_expiry(self, value):
        clean = value.replace('/', '')
        if not re.fullmatch(r'\d{4}', clean):
            raise serializers.ValidationError('Expiry must be MMYY or MM/YY format.')
        month = int(clean[:2])
        if not (1 <= month <= 12):
            raise serializers.ValidationError('Invalid expiry month.')
        # ATMOS API YYMM format talab qiladi
        return clean[2:] + clean[:2]


class ConfirmPaymentSerializer(serializers.Serializer):
    transaction_id = serializers.CharField(max_length=255)
    otp            = serializers.CharField(min_length=4, max_length=8)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('OTP must contain digits only.')
        return value


class RetryOtpSerializer(serializers.Serializer):
    transaction_id = serializers.CharField(max_length=255)


class MpsStartSerializer(serializers.Serializer):
    amount      = serializers.IntegerField(min_value=100, help_text='Tiyinlarda')
    account     = serializers.CharField(max_length=255)
    pan         = serializers.CharField(min_length=16, max_length=19)
    expiry      = serializers.CharField(min_length=4, max_length=5)
    cvc2        = serializers.CharField(min_length=3, max_length=4)
    card_name   = serializers.CharField(max_length=255)
    invoice_id  = serializers.CharField(max_length=255, required=False, default='')

    def validate_account(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('Account must contain digits only.')
        if Order.objects.filter(pk=value, conference_registration__isnull=False).exists():
            raise serializers.ValidationError('Please use Payme for TESOL conference payments.')
        return value

    def validate_pan(self, value):
        digits = re.sub(r'\D', '', value)
        if len(digits) != 16:
            raise serializers.ValidationError('Card number must be exactly 16 digits.')
        return digits

    def validate_expiry(self, value):
        clean = value.replace('/', '')
        if not re.fullmatch(r'\d{4}', clean):
            raise serializers.ValidationError('Expiry must be MMYY or MM/YY format.')
        month = int(clean[:2])
        if not (1 <= month <= 12):
            raise serializers.ValidationError('Invalid expiry month.')
        return clean  # MPS MMYY formatni talab qiladi

    def validate_cvc2(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('CVC2 must contain digits only.')
        return value


class MpsApplySerializer(serializers.Serializer):
    transaction_id = serializers.CharField(max_length=255)


class AtmosTransactionSerializer(serializers.ModelSerializer):
    amount_uzs = serializers.SerializerMethodField()

    class Meta:
        model = AtmosTransaction
        fields = [
            'id', 'transaction_id', 'amount', 'amount_uzs',
            'account', 'card_number_masked', 'status',
            'atmos_transaction_id', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_amount_uzs(self, obj):
        return obj.amount_uzs
