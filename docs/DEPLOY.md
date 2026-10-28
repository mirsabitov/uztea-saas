# Deploy — UzTEA Workspace release

Branch `feature/uztea-workspace-ui` → PR into `main`. Django 5.2, same stack, **no new
Python packages** (Playwright and openpyxl were already in `requirements.txt`).

## What changed and where
| Area | Where | Notes |
|---|---|---|
| Staff workspace (dashboard, people, payments, partners, settings, messages) | `workspace/` → `/workspace/` | Staff-only. `/admin/` unchanged. |
| Membership status (Active / Renewal due / Expired) | `app/membership_lifecycle.py` | Computed from payments, nothing stored. |
| Payment status helper | `app/payment_status.py` | Same rules as before; admin column uses it. |
| SMS (Eskiz) + email from the workspace, message log | `workspace/sms.py`, `workspace/messaging.py` | |
| SaaS Settings: organisation, logos, default language | `/workspace/saas/` | |
| Languages EN / UZ / RU | `workspace/i18n.py` | Dictionary, no gettext needed. |
| Brevo for all email | `root/settings.py` (EMAIL_* switch) | Only when `BREVO_*` env is set. |
| Certificates: designer, numbering, PDF, issuing | `certificates/` → `/workspace/certificates/` | PDFs via Playwright Chromium. |
| Certificate portal | `certificates/` → `certificates.uztea.uz` (= `/certificates/`) | `certificates.middleware.CertificatesHostMiddleware` |
| Member area "My profile" (login, edit profile, photo, email opt-in) | `cabinet/` → `/account/` | Members are never staff. |
| Public membership form look | `static/forms/membership-modern.css` (linked from `templates/membership_form.html`) | Fields and JS unchanged. |
| Admin | `app/admin.py` | Membership list shows "Email updates" column + filter. |
| Settings | `root/settings.py` | New apps `workspace`, `certificates`, `cabinet`; host middleware; Brevo block. |
| URLs | `root/urls.py` | `/workspace/`, `/certificates/`, `/account/`, `/set-language/`. |

Existing URLs, payment callbacks and public forms are unchanged.

## Database
`migrate` **only adds tables** (no change to existing tables):
`workspace_*` (messagelog, organizationsettings, event, benefit), `certificates_*`
(certificatetemplate, certificate, certificatesequence), `cabinet_*` (memberprofile,
profilechange). Back up the DB first anyway.

## Steps
```bash
# 0. backup PostgreSQL + media/
git fetch origin && git checkout main && git pull        # after the PR is merged
pip install -r requirements.txt
python -m playwright install --with-deps chromium        # certificate PDFs / membership cards
python manage.py migrate
python manage.py collectstatic --noinput
# restart gunicorn/uwsgi (or the service you use)
```

`.env` additions (see `.env.example`):
```
BREVO_SMTP_LOGIN=...            # Brevo SMTP login
BREVO_SMTP_KEY=...              # Brevo SMTP key → all mail goes via Brevo
ESKIZ_EMAIL=...  ESKIZ_PASSWORD=...  ESKIZ_FROM=4546
CERTIFICATES_BASE_URL=https://certificates.uztea.uz
CABINET_BASE_URL=https://membership.uztea.uz   # where /account/ is served
ALLOWED_HOSTS=...,certificates.uztea.uz
CSRF_TRUSTED_ORIGINS=...,https://certificates.uztea.uz
```

Web server / DNS:
- `certificates.uztea.uz` → same server and same Django app (add to nginx `server_name`
  and the TLS certificate).
- Serve `/media/` (uploaded logos, signatures, stamps, member photos, cached PDFs).
- Brevo: verify the uztea.uz sender (SPF + DKIM). Eskiz: approve the SMS texts.

## Smoke test after deploy
- `/admin/`, `/apply/`, `/tesol/`, `/30years/` open; a test payment callback still works.
- `/workspace/` (staff login) → Home dashboard loads.
- Send yourself a test email and SMS from People.
- Issue a certificate to yourself, open the emailed link, verify the number on
  `https://certificates.uztea.uz`.
- People → a member → "Invite to cabinet" → set password → `/account/` → Edit profile.

## Rollback
`git checkout <previous tag/commit>`, restart. The new tables can stay; old code ignores them.

## Notes
- `manage.py workspace_demo_data` refuses to run in production (DEBUG + SQLite only).
- Staff permissions: give groups `workspace | message | add/view`, `workspace | event`,
  `workspace | benefit`, `certificates | *` as needed; superusers see everything.
