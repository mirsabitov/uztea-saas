# CLAUDE.md — UzTEA SaaS

Back-office for UzTEA (Uzbekistan Teachers of English Association). The public site
uztea.uz runs on Tilda and links into the forms served by this Django project.
Owner: Mirjalol. Talk to him in Uzbek (Latin script) unless he writes in another language;
code, comments, commit messages and identifiers stay in English.

## Stack
- Python, Django 5.2, DRF, SimpleJWT, drf-spectacular / drf-yasg
- PostgreSQL (enabled when `POSTGRES_DB` is set), Redis cache at `redis://127.0.0.1:6379/1`
- Jazzmin admin (custom CSS `static/uztea_admin_v20.css`, JS `static/uztea_admin.js`),
  django-import-export, django-ckeditor
- Playwright renders membership cards to PNG (`app/card_render.py`)
- Dev machine is Windows; virtualenv at `.venv/` (`.venv/Scripts/python`)

## Commands
```bash
make install-req      # pip install -r requirements.txt
make mig              # makemigrations + migrate
make admin            # createsuperuser
make static           # collectstatic -> staticfiles/ (gitignored)
.venv/Scripts/python manage.py runserver
.venv/Scripts/python manage.py test            # all tests
.venv/Scripts/python manage.py test app.test_conference payme.test_auth
```
On Unix use `make PYTHON=python3 PIP=pip3` or `.venv/bin/python`.

## Layout
| Path | What it is |
|---|---|
| `root/` | settings, urls, wsgi/asgi, swagger |
| `app/` | core: `Membership` (+ proxy `PendingPayment`), `MembershipTypeConfig`, `Partner`, `TeacherBank`, `ConferenceRegistration` (TESOL), `AnniversaryRegistration` (30 years); pricing, notifications (Telegram + welcome email), card rendering, JWT/OTP auth API |
| `click/` | `Order` (shared order model used by all payment providers), `PromoCode`, Click webhook, signature check, fiscal data submission, payment status pages |
| `payme/` | Payme JSON-RPC merchant API, `PaymeConfig`, `PaymeTransaction`. Docs: `payme/DOCS.md`, `payme/TESOL.md` |
| `atmos/` | Atmos card payments (OTP flow, MPS), `AtmosTransaction` |
| `templates/` | public forms (`membership_form.html`, `conference_form.html`, `anniversary_form.html`), payment pages, membership cards, admin overrides |
| `static/` | source static files; `staticfiles/` is generated |

## Main routes
- `/apply/` membership form → `/payments/click/pay/<order_pk>/` → `/payments/click/status/<order_pk>/`
- `/tesol/` conference registration, `/tesol/payment/<uuid>/`
- `/30years/` anniversary registration
- `/membership/<pk>/card/`, `/card-preview/`
- `/auth/api/...` register, login, token refresh, me, OTP send/verify
- Payment callbacks: `/payments/click/webhook/`, `/payments/payme/webhook/`,
  `/payments/atmos/api/callback/`
- `/admin/` (includes custom email composer for memberships, Click tools & logs)

## Rules
- **Secrets only via `.env`** (template: `.env.example`). Never hardcode keys, never commit
  `.env`, DB dumps, member exports, or `media/`.
- **Payments are high-risk.** Any change to Click / Payme / Atmos code, `Order` status logic or
  webhook handling needs tests and must keep signature/auth verification intact. Never point
  production checkout (`PAYME_ENV=prod`) at a local or test database.
- **Migrations:** never edit or delete applied migrations; add new ones. App migrations jump
  0006 → 0009 on purpose (0009 depends on 0006). Run `makemigrations --check` before committing.
- Member data is personal data (names, phones, emails): don't log it unnecessarily, don't
  print it in tests output, use fake data in tests and fixtures.
- Keep changes small and focused; one topic per branch/PR. Run the test suite before pushing.
- Ask Mirjalol before: changing the DB schema of existing tables, touching production
  settings/deploy, sending real emails/Telegram messages, or deleting files.

## Known issues / backlog (from initial review, 2026-10-26)
1. CSRF middleware is commented out in `root/settings.py` — re-enable and exempt only the
   payment webhooks that need it.
2. `ALLOWED_HOSTS` defaults to `['*', <old ngrok host>]`; `CORS_ALLOW_ALL_ORIGINS = True`.
3. JWT access/refresh lifetime ~100 days; password validators disabled.
4. Redis URL is hardcoded — move to env (`REDIS_URL`).
5. `static/` has 21 unused `uztea_admin_v*.css` versions (only v20 is used).
6. `django-ckeditor` (CKEditor 4) is unmaintained — plan replacement (e.g. django-ckeditor-5 / TinyMCE).
7. `requirements.txt` lists `requests` twice; `makefile` package is unnecessary.
8. Log file `click_payments.log` is written into the project root — move to a logs dir.

## UzTEA Workspace (`/workspace/`) — approved decisions
Phases and status live in `docs/ROADMAP.md`.
- The workspace is a separate staff-only Django app (`workspace/`) at `/workspace/`.
  The classic `/admin/` stays as it is and is reachable from "More tools".
- Plain Django templates + one vanilla CSS/JS file (`workspace/static/workspace/`).
  No frontend framework, no new dependencies.
- The workspace reads data. Every change (edit, add, import/export, bulk actions,
  payment tools) goes through the existing admin views, so admin permissions stay the
  single source of truth. Bulk actions POST to the admin changelist.
- Navigation: Home (live dashboard), People (Members / Teachers Bank / All contacts /
  Messages), Forms & Events, Payments, Partners, Settings, then a separate Website item
  (uztea.uz content — placeholder for its own phase), plus More tools and the user menu.
- Payment status is computed by `app/payment_status.py` (shared with the admin column) and
  is never merged with membership status. Approved: it follows the latest order, so a
  member who paid and later had a failed order shows "Failed".
- Membership status (approved 2026-10-27), computed in `app/membership_lifecycle.py`, not
  stored: Active from a successful payment for 12 months (365 days, as in the welcome
  email) after the latest successful payment; "Renewal due" in the last 30 days;
  "Expired" after; "Pending payment" (orders, none paid) / "No payment record" (no orders,
  e.g. imported members).
- Institutional members 2–5 are shown as separate people (All contacts, profile) with the
  institution's status. They are not separate records yet (see ROADMAP "Person").
- Messaging: SMS via Eskiz (`workspace/sms.py`, `ESKIZ_*` in .env) and email using the
  admin composer's templates/senders. Every attempt is logged in `workspace.MessageLog`.
  Permissions: `workspace.add_messagelog` to send, `workspace.view_messagelog` for history,
  plus view permission on the recipient list. Without Eskiz credentials SMS runs in test
  mode on DEBUG servers and is disabled elsewhere. Sending always needs a confirmation tick.
- All workspace views are `csrf_protect`ed (the project's CSRF middleware is off).
- Dark / light mode: CSS tokens in `workspace.css`; choice stored in localStorage, else the
  OS setting.
- Public membership form keeps its markup, fields and JS; the modern look is the extra
  stylesheet `static/forms/membership-modern.css` (remove the <link> to roll back).
- Languages (approved 2026-10-27): workspace, member cabinet and certificate portal in
  English / Uzbek / Russian. Translations live in `workspace/i18n.py` (English text is the
  key; `{% t "…" %}` and `|tr:lang`); missing lines fall back to English. No gettext.
  Order: person's choice (session) > SaaS Settings default > English.
- SaaS Settings (header button, `/workspace/saas/`): organisation details + default
  language, stored in `workspace.OrganizationSettings` (single row).
- Brevo: all email goes through Brevo's SMTP relay when `BREVO_SMTP_LOGIN` /
  `BREVO_SMTP_KEY` are set (root/settings.py); otherwise the old EMAIL_* settings apply.
- Certificates (`certificates` app): templates designed in the workspace (positions in %
  of the page, same rules in the designer JS and `certificates/render.py`), PDFs by
  Playwright/Chromium, numbers `UZTEA-YYYY-NNNNNN` from `CertificateSequence` (never
  reused). Issued to selected members or an Excel/CSV/pasted list; emailed as a link.
  Public portal `certificates.uztea.uz` (= `/certificates/` via
  `CertificatesHostMiddleware`): lookup by email or membership ID only emails the links
  to the address on file (nothing shown on screen); verification by number is public.
- Member cabinet (`cabinet` app, `/account/`): Django users with username = email, never
  staff. Accounts are created, invited and reset with the same emailed set-password link
  (Django token, 3 days). Shows membership status, card, payments, event registrations,
  certificates, benefits (active members, by type) and published upcoming events.
  Courses: "Coming soon".
- Events (`workspace.Event`, Forms & Events → Events) and member benefits
  (`workspace.Benefit`, Partners → Bonuses & offers) are managed in the workspace.
- Records from different tables are never merged. The same email in several lists is
  only pointed out ("Also in").
- Unbuilt features are labelled "Preview" / "Next phase" and their buttons are disabled.
  Form Studio is a client-side sandbox that saves nothing.
- Logos: `workspace/static/workspace/img/logo-{white,navy,blue}.png` (white on dark,
  navy on light, blue for accents). Never crop or stretch them.
- Demo data: `manage.py workspace_demo_data` (`--clear` to remove) runs only with
  DEBUG + SQLite. Demo records use `@demo.uztea.test` emails and show a "Demo data" badge.
  Optional local login from `DEMO_ADMIN_USERNAME` / `DEMO_ADMIN_PASSWORD` in `.env`.
- Local dev without PostgreSQL: in `.env` set `DB_ENGINE=django.db.backends.sqlite3`
  and `POSTGRES_DB=db.sqlite3`.

## Future
uztea.uz (currently Tilda) will later be rebuilt in Python as a replica and served
alongside / integrated with this project.
