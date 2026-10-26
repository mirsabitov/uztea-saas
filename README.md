# UzTEA SaaS

Back-office for the Uzbekistan Teachers of English Association (UzTEA): membership
registration and database, seminar / conference / anniversary event forms, membership
cards, admin email composer, and online payments (Click, Payme, Atmos).

The public website (uztea.uz) currently runs on Tilda and links into the forms served here.

## Stack
- Python / Django 5.2, Django REST Framework, SimpleJWT
- PostgreSQL, Redis (cache)
- Jazzmin admin, django-import-export, CKEditor
- Playwright (membership card PNG rendering)

## Apps
| App | Purpose |
|---|---|
| `app` | Memberships, membership types & pricing, partners, conference and anniversary registrations, cards, notifications |
| `click` | Click payments, orders, promo codes |
| `payme` | Payme merchant API (see `payme/DOCS.md`, `payme/TESOL.md`) |
| `atmos` | Atmos payments |
| `root` | Project settings and URLs |

## Local setup
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows (Unix: .venv/bin/pip)
cp .env.example .env                            # then fill in values
make mig        # makemigrations + migrate
make admin      # create superuser
make static     # collectstatic
python manage.py runserver
```

## URLs
- `/admin/` — admin panel
- `/payments/click/`, `/payments/payme/`, `/payments/atmos/` — payment callbacks
- other public routes: see `app/urls.py`

## Secrets
All credentials are read from `.env` (see `.env.example`). Never commit `.env`,
database dumps, or member data exports.
