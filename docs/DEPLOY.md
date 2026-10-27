# Putting the workspace on the server

Branch: `feature/uztea-workspace-ui`. Merge into `main` only after the owner approves.

## What changes in the database
`migrate` only **adds** tables; no existing table or column is changed:
`workspace_messagelog`, `workspace_organizationsettings`, `workspace_event`,
`workspace_benefit`, `certificates_certificatetemplate`, `certificates_certificate`,
`certificates_certificatesequence`. Back up the database first anyway.

## Steps
1. Back up PostgreSQL and `media/`.
2. `git fetch && git checkout <the approved branch or main>`
3. `pip install -r requirements.txt`
4. Chromium for certificate PDFs (and membership cards):
   `python -m playwright install --with-deps chromium`
5. `python manage.py migrate`
6. `python manage.py collectstatic --noinput`
7. Add to the server's `.env` (see `.env.example`):
   - `BREVO_SMTP_LOGIN`, `BREVO_SMTP_KEY` — all email goes through Brevo once set.
     Verify `info@uztea.uz` / the uztea.uz domain (SPF + DKIM) in Brevo first.
   - `ESKIZ_EMAIL`, `ESKIZ_PASSWORD`, `ESKIZ_FROM` — SMS. Get the SMS texts approved
     as templates in the Eskiz cabinet.
   - `CERTIFICATES_BASE_URL=https://certificates.uztea.uz`
   - `CABINET_BASE_URL=https://<site where /account/ is served>` (defaults to `SITE_BASE_URL`)
   - `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`: add `certificates.uztea.uz`
     (`https://certificates.uztea.uz` for CSRF).
8. DNS: point `certificates.uztea.uz` at the server; add it to the web server config
   (nginx `server_name`) and the TLS certificate. The same Django app serves it.
9. Make sure `/media/` is served (uploaded signatures, stamps, logos, cached PDFs).
10. Restart the app server.

## After deploy — check
- `/workspace/` opens for staff; `/admin/` still works.
- `/apply/`, `/tesol/`, `/30years/` and the payment callbacks still work.
- Send a test email and a test SMS to yourself from People.
- Issue one certificate to yourself, open the emailed link, verify the number at
  `https://certificates.uztea.uz`.
- Invite yourself to the cabinet and sign in at `/account/`.

## Permissions to give staff
Create groups in the admin (Users & groups):
- **Membership team**: view/change membership, pending payment, teachers bank;
  `workspace | message | add/view` to send SMS / email.
- **Events team**: `workspace | event` add/change/view; certificates add/change/view.
- **Finance**: click order, atmos, payme, promo code (view).
Superusers see everything.

## Not for production
`manage.py workspace_demo_data` refuses to run unless DEBUG and SQLite.
