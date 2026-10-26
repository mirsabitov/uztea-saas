"""Fill a LOCAL database with clearly marked demo records for the workspace.

Refuses to run unless DEBUG is on and the database is SQLite, so it can never
touch the production PostgreSQL database. Every demo record uses an
@demo.uztea.test email (or "Demo data" as source) and is shown with a
"Demo data" badge. `--clear` removes only those records.

Optional local login: set DEMO_ADMIN_USERNAME and DEMO_ADMIN_PASSWORD in .env
to create a local superuser for checking the UI.
"""
import os
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from app.models import (
    AnniversaryRegistration,
    ConferenceRegistration,
    Membership,
    MembershipTypeConfig,
    Partner,
    TeacherBank,
)
from atmos.models import AtmosTransaction
from click.models import Order, PromoCode
from payme.models import PaymeTransaction
from workspace.people import DEMO_EMAIL_DOMAIN

DEMO_SOURCE = 'Demo data'

FIRST = ['Aziza', 'Diyor', 'Nilufar', 'Bekzod', 'Malika', 'Samandar', 'Madina', 'Jasur', 'Dilnoza', 'Otabek',
         'Gulnora', 'Sardor', 'Kamola', 'Rustam', 'Shahnoza', 'Timur', 'Zarina', 'Akmal', 'Feruza', 'Bobur']
LAST = ['Karimova', 'Tashmetov', 'Saidova', 'Akhmedov', 'Kholmatova', 'Aliev', 'Rasulova', 'Yusupov',
        'Nazarova', 'Ergashev', 'Ismoilova', 'Rakhimov', 'Usmonova', 'Sobirov', 'Mirzaeva', 'Qodirov']
CITIES = ['Tashkent', 'Samarkand', 'Bukhara', 'Namangan', 'Fergana', 'Andijan', 'Nukus', 'Karshi']
SCHOOLS = ['School No. 12', 'Westminster International University', 'Uzbekistan State World Languages University',
           'Lyceum No. 3', 'Bright Future Learning Centre', 'Samarkand State University', 'Presidential School']
TYPES = [('basic', 'Basic Membership', 50000), ('student', 'Student / Early Career / Retired', 100000),
         ('teacher', 'Individual Teacher', 150000), ('institutional', 'Institutional Membership', 1000000)]


def demo_email(name, n):
    return f"{name.lower().replace(' ', '.')}{n}@{DEMO_EMAIL_DOMAIN}"


class Command(BaseCommand):
    help = 'Create (or --clear) clearly marked demo data in a local SQLite database.'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Remove demo records only.')
        parser.add_argument('--members', type=int, default=44)

    def handle(self, *args, **opts):
        if not settings.DEBUG or connection.vendor != 'sqlite':
            raise CommandError('Demo data is only allowed with DEBUG=True on a local SQLite database.')

        with transaction.atomic():
            self.clear()
            if opts['clear']:
                self.stdout.write(self.style.SUCCESS('Demo records removed.'))
                return
            self.create(opts['members'])
        self.create_local_admin()

    def clear(self):
        demo = f'@{DEMO_EMAIL_DOMAIN}'
        orders = Order.objects.filter(membership__email__endswith=demo) | Order.objects.filter(
            conference_registration__email__endswith=demo)
        order_ids = [str(pk) for pk in orders.values_list('pk', flat=True)]
        AtmosTransaction.objects.filter(account__in=order_ids).delete()
        PaymeTransaction.objects.filter(order_id__in=[int(i) for i in order_ids]).delete()
        orders.delete()
        Membership.objects.filter(email__endswith=demo).delete()
        ConferenceRegistration.objects.filter(email__endswith=demo).delete()
        AnniversaryRegistration.objects.filter(email__endswith=demo).delete()
        TeacherBank.objects.filter(email__endswith=demo).delete()
        Partner.objects.filter(email__endswith=demo).delete()
        PromoCode.objects.filter(code__startswith='DEMO').delete()

    def create(self, member_count):
        rnd = random.Random(30)  # stable demo set
        now = timezone.now()

        for code, name, price in TYPES:
            MembershipTypeConfig.objects.get_or_create(
                membership_type=code, defaults={'name': name, 'price': Decimal(price)})
        prices = {c.membership_type: c.price for c in MembershipTypeConfig.objects.all()}
        promo = PromoCode.objects.create(code='DEMO100', discount_percent=100, max_uses=20, used_count=3)
        PromoCode.objects.create(code='DEMO50', discount_percent=50, is_active=False)

        for i in range(member_count):
            first, last = rnd.choice(FIRST), rnd.choice(LAST)
            full = f'{first} {last}'
            mtype = rnd.choices([t[0] for t in TYPES], weights=[3, 4, 5, 1])[0]
            pending = i % 7 == 3
            m = Membership.objects.create(
                full_name=full, email=demo_email(full, i), phone_number=f'+99890{rnd.randint(1000000, 9999999)}',
                gender=rnd.choice(['male', 'female']), nationality='Uzbek', country='Uzbekistan',
                region_city=rnd.choice(CITIES), position=rnd.choice(['teacher', 'teacher', 'lecturer', 'student', 'trainer']),
                institution_name=rnd.choice(SCHOOLS),
                institution_type=rnd.choice(['school', 'university', 'training']), experience=rnd.choice(['0-2', '3-5', '6-10', '10+']),
                membership_type=mtype, preferred_language=rnd.choice(['en', 'uz', 'ru']),
                contact_method=rnd.choice(['email', 'telegram', 'both']), payment_method=rnd.choice(['atmos', 'payme']),
                interests='Methodology, Assessment', agree_terms=True, consent_data=True, agree_communication=True,
                is_pending_payment=pending,
            )
            created = now - timedelta(days=rnd.randint(1, 420), hours=rnd.randint(0, 23))
            Membership.objects.filter(pk=m.pk).update(created_at=created)

            outcome = 'none' if i % 11 == 5 else rnd.choices(['paid', 'pending', 'failed', 'atmos_ok', 'atmos_otp'], [5, 2, 1, 3, 1])[0]
            if pending and outcome in ('paid', 'atmos_ok'):
                outcome = 'pending'
            if outcome == 'none':
                continue
            order = Order.objects.create(
                membership=m, amount=prices.get(mtype, Decimal(100000)),
                status={'paid': 'paid', 'failed': 'failed', 'atmos_ok': 'processing'}.get(outcome, 'pending'),
                click_trans_id=f'DEMO-{rnd.randint(100000, 999999)}' if outcome == 'paid' else None,
                promocode=promo if i % 13 == 0 else None,
            )
            Order.objects.filter(pk=order.pk).update(created_at=created, updated_at=created + timedelta(minutes=5))
            if outcome in ('atmos_ok', 'atmos_otp'):
                txn = AtmosTransaction.objects.create(
                    transaction_id=f'demo-{order.pk}-{rnd.randint(1000, 9999)}', account=str(order.pk),
                    amount=int(order.amount * 100), card_number_masked='8600 **** **** ' + str(rnd.randint(1000, 9999)),
                    status='SUCCESS' if outcome == 'atmos_ok' else 'OTP_SENT')
                AtmosTransaction.objects.filter(pk=txn.pk).update(created_at=created + timedelta(minutes=2))
            if i % 9 == 0 and outcome == 'paid':
                PaymeTransaction.objects.create(transaction_id=f'demo-payme-{order.pk}', order=order,
                                                amount=order.amount, state=2, performed_at=created + timedelta(minutes=3))

        for i in range(24):
            full = f'{rnd.choice(FIRST)} {rnd.choice(LAST)}'
            TeacherBank.objects.create(full_name=full, email=demo_email(full, 100 + i),
                                       phone_number=f'+99891{rnd.randint(1000000, 9999999)}', source=DEMO_SOURCE)
        # A few people who are also members, to show "Also in" without merging.
        for m in Membership.objects.filter(email__endswith=f'@{DEMO_EMAIL_DOMAIN}')[:3]:
            TeacherBank.objects.create(full_name=m.full_name, email=m.email, phone_number=m.phone_number, source=DEMO_SOURCE)
            AnniversaryRegistration.objects.create(full_name=m.full_name, email=m.email, phone_number=m.phone_number,
                                                   membership_status='yes', event_communication=True)

        companies = ['British Council (demo)', 'American Councils (demo)', 'Regional Education Office (demo)',
                     'Cambridge Partner Centre (demo)', 'Teacher Training Institute (demo)', 'EdTech Startup (demo)']
        for i, company in enumerate(companies):
            full = f'{rnd.choice(FIRST)} {rnd.choice(LAST)}'
            Partner.objects.create(full_name=full, email=demo_email(full, 200 + i), company_name=company,
                                   position=rnd.choice(['Programme manager', 'Director', 'Coordinator']),
                                   phone_number=f'+99871{rnd.randint(1000000, 9999999)}',
                                   country='Uzbekistan', source=DEMO_SOURCE)

        for i in range(8):
            full = f'{rnd.choice(FIRST)} {rnd.choice(LAST)}'
            reg = ConferenceRegistration.objects.create(
                full_name=full, email=demo_email(full, 300 + i), job_title='English teacher',
                organization=rnd.choice(SCHOOLS), country='Uzbekistan',
                mobile_phone=f'+99893{rnd.randint(1000000, 9999999)}', accepted_terms=True)
            if i % 2 == 0:
                Order.objects.create(conference_registration=reg, amount=Decimal(250000),
                                     status='paid' if i % 4 == 0 else 'pending')
        for i in range(12):
            full = f'{rnd.choice(FIRST)} {rnd.choice(LAST)}'
            AnniversaryRegistration.objects.create(
                full_name=full, email=demo_email(full, 400 + i), phone_number=f'+99894{rnd.randint(1000000, 9999999)}',
                membership_status=rnd.choice(['yes', 'not_yet']), event_communication=True,
                future_updates=rnd.random() > .3, photos_videos=rnd.random() > .5)

        self.stdout.write(self.style.SUCCESS(f'Demo data created: {member_count} memberships plus contacts, orders and registrations.'))

    def create_local_admin(self):
        username = os.getenv('DEMO_ADMIN_USERNAME')
        password = os.getenv('DEMO_ADMIN_PASSWORD')
        if not (username and password):
            return
        User = get_user_model()
        user, _ = User.objects.get_or_create(username=username, defaults={'first_name': 'Demo', 'last_name': 'Admin'})
        user.is_staff = user.is_superuser = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f'Local admin "{username}" is ready (password from .env).'))
