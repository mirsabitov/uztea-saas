import random
import logging

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings

from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger('app')

OTP_TTL = 300          # 5 minutes
OTP_CACHE_PREFIX = 'auth_otp:'


def _cache_get(key):
    try:
        return cache.get(key)
    except Exception as exc:
        logger.warning('auth | cache get failed (%s): %s', key, exc)
        return None


def _cache_set(key, value, ttl):
    try:
        cache.set(key, value, ttl)
        return True
    except Exception as exc:
        logger.warning('auth | cache set failed (%s): %s', key, exc)
        return False


def _cache_delete(key):
    try:
        cache.delete(key)
    except Exception:
        pass


# ── helpers ──────────────────────────────────────────────────────────── #

def _tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }


def _user_payload(user):
    return {
        'id': user.id,
        'full_name': (f'{user.first_name} {user.last_name}').strip() or user.username,
        'email': user.email,
    }


def _ok(data, http_status=200):
    return Response({'success': True, **data}, status=http_status)


def _err(message, code='ERROR', http_status=400):
    return Response({'success': False, 'error': {'message': message, 'code': code}},
                    status=http_status)


# ── serializers ──────────────────────────────────────────────────────── #

class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=6, write_only=True)
    otp = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(username=value).exists() or User.objects.filter(email=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def validate_password(self, value):
        validate_password(value)
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class OtpSendSerializer(serializers.Serializer):
    email = serializers.EmailField()


class OtpVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=4, max_length=8)


# ── views ────────────────────────────────────────────────────────────── #

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def register(request):
    s = RegisterSerializer(data=request.data)
    if not s.is_valid():
        field, errs = next(iter(s.errors.items()))
        return _err(f'{field}: {errs[0]}', code='VALIDATION_ERROR')

    data = s.validated_data
    email = data['email']

    # If an OTP was issued for this email, require it to match
    cached = _cache_get(OTP_CACHE_PREFIX + email)
    if cached is not None:
        if str(data.get('otp') or '') != str(cached):
            return _err('Invalid or expired verification code.', code='OTP_INVALID')
        _cache_delete(OTP_CACHE_PREFIX + email)

    parts = data['full_name'].strip().split(' ', 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ''

    user = User.objects.create_user(
        username=email,
        email=email,
        password=data['password'],
        first_name=first_name,
        last_name=last_name,
    )
    logger.info('auth | register | user=%s', email)
    return _ok({'user': _user_payload(user), 'tokens': _tokens_for(user)},
               http_status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def login(request):
    s = LoginSerializer(data=request.data)
    if not s.is_valid():
        return _err('Email and password are required.', code='VALIDATION_ERROR')

    email = s.validated_data['email'].strip().lower()
    password = s.validated_data['password']

    # username is the email; fall back to lookup by email field
    user = authenticate(username=email, password=password)
    if user is None:
        try:
            u = User.objects.get(email=email)
            user = authenticate(username=u.username, password=password)
        except User.DoesNotExist:
            user = None

    if user is None:
        return _err('Incorrect email or password.', code='AUTH_FAILED', http_status=401)
    if not user.is_active:
        return _err('This account is disabled.', code='ACCOUNT_DISABLED', http_status=403)

    logger.info('auth | login | user=%s', email)
    return _ok({'user': _user_payload(user), 'tokens': _tokens_for(user)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return _ok({'user': _user_payload(request.user)})


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def otp_send(request):
    s = OtpSendSerializer(data=request.data)
    if not s.is_valid():
        return _err('A valid email is required.', code='VALIDATION_ERROR')

    email = s.validated_data['email'].strip().lower()
    code = f'{random.randint(0, 999999):06d}'
    _cache_set(OTP_CACHE_PREFIX + email, code, OTP_TTL)

    try:
        send_mail(
            subject='Your UzTEA verification code',
            message=f'Your UzTEA verification code is: {code}\n\nIt expires in 5 minutes.',
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@uztea.uz'),
            recipient_list=[email],
            fail_silently=True,
        )
    except Exception as exc:
        logger.error('auth | otp_send | email failed: %s', exc)

    logger.info('auth | otp_send | email=%s', email)
    return _ok({'message': 'Verification code sent.'})


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def otp_verify(request):
    s = OtpVerifySerializer(data=request.data)
    if not s.is_valid():
        return _err('Email and code are required.', code='VALIDATION_ERROR')

    email = s.validated_data['email'].strip().lower()
    cached = _cache_get(OTP_CACHE_PREFIX + email)
    if cached is None:
        return _err('Verification code expired. Please request a new one.', code='OTP_EXPIRED')
    if str(s.validated_data['otp']) != str(cached):
        return _err('Incorrect verification code.', code='OTP_INVALID')

    return _ok({'message': 'Email verified.'})
