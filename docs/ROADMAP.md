# UzTEA Workspace — roadmap

One section at a time. A phase starts only after the previous one is reviewed and approved.
Decisions that are approved go into `CLAUDE.md`.
Branch: `feature/uztea-workspace-ui` (not pushed, not merged, not deployed).

## Phase 1 — Interface and navigation · approved (2026-10-27)
- Staff-only `/workspace/` app with sidebar, header, the original logos and a shared style.
- People → Members: search (name, email, institution, membership ID), filters, sort,
  pagination, column toggles, bulk actions (run by the admin), row → Member preview,
  full profile with 7 tabs that show every existing field.
- People → Teachers Bank and All contacts (every list, one row per record, "Also in" hints).
- Forms & Events: the three existing forms with real response counts, share link, export,
  templates; Form Studio as a sandbox (add, edit, duplicate, reorder, delete fields; preview).
- Payments: Orders, Pending Payments, ATMOS, Payme, Promo Codes, Click Tools (read-only).
- Partners, Settings, More tools.
- Home dashboard (live from the database) with time ranges, tiles, charts, tooltips and
  table views; every month labelled on 12-month charts.

## Phase 2 — People and the membership lifecycle · approved (2026-10-27)
Done:
- Membership status from payments (Active / Renewal due / Expired / Pending payment /
  No payment record), "Valid until", quick views, status filter and renewal sort.
- Dashboard: Active members tile, "renewal due" in Needs attention.
- Institutional members 2–5 shown as people (All contacts, profile).
- SMS (Eskiz) and email to one or many people from Members, Teachers Bank and Partners;
  message history (People → Messages) and in each member's activity.
- Dark / light mode, Website menu item (placeholder), modern look for the public
  membership form (same questions and logic).

Open decisions:
- Separate "Person" record (one person across membership, events, Teachers Bank,
  partners) — not decided. Institutional members are shown, not stored separately.
- "Cancelled" membership status has no data source yet (no cancel action exists).
- Members imported from the old site with no orders show "No payment record". Decide how
  to give them a start date (e.g. import a paid-on date column).
- Eskiz: production credentials, approved SMS templates, sender name.

## Phase 2b — SaaS Settings, languages, Brevo, certificates, member cabinet · in review
Done:
- SaaS Settings button in the header: organisation details, default language; every
  person can switch English / O'zbekcha / Русский (workspace, cabinet, certificate portal).
- Brevo: all email goes through Brevo when its SMTP key is set.
- Events (Forms & Events → Events) and member benefits (Partners → Bonuses & offers).
- Certificates: template designer (drag text and images; signature, stamp, UzTEA and
  partner logos, background; fonts, colours, frame), PDF preview, numbering
  UZTEA-YYYY-NNNNNN, issue to selected members or from Excel/CSV/pasted list, email
  links, revoke / re-send, ZIP per batch.
- certificates.uztea.uz: find by email or membership ID (links emailed to the address
  on file), verify by number, download.
- Member cabinet `/account/`: create account / reset password by emailed link, admin
  invitations (one or many), dashboard with membership, card, payments, events,
  certificates, bonuses, upcoming events, profile; courses "Coming soon".

Open decisions:
- Which address serves the cabinet (e.g. `uztea.uz/account/` or a subdomain).
- Whether members may edit their own profile details.

## Combined go-live step (after Phase 2b is approved)
See `docs/DEPLOY.md`.
Push the branch, open a PR (no merge without approval), find out how production is
deployed, test on staging with real data, run `migrate` (adds the `workspace_messagelog`
table only) and `collectstatic`, add `ESKIZ_*` to the server's .env.

## Phase 3 — Form Studio: build forms and collect responses
Form / Field / Submission models, draft → preview → publish → responses → close (stop
accepting answers) → archive, versioning so edits don't break earlier answers.

## Phase 4 — Events: registration, capacity, attendees
Event model (date, place, capacity, deadline), link to forms, move TESOL / 30th
Anniversary in without changing their URLs or data.

## Phase 5 — Payments for new forms
Connect forms and events to the existing Click / Payme / Atmos flows without changing
their verification and callbacks.

## Phase 6 — Partners
Partner database with benefits, discounts and offers, links to events, SMS / email.

## Phase 7 — Settings
Edit organisation details; workspace language Uzbek / Russian / English.

## Phase 8 — Website (uztea.uz content)
News, events and pages of uztea.uz managed from the workspace.

## Last — security and technical debt (agreed to do at the end)
- `/membership/<pk>/card/` is public and keyed by a sequential id.
- CSRF middleware off (workspace views are protected individually), `ALLOWED_HOSTS`,
  CORS open, JWT lifetime, password validators.
- Redis URL to env, log directory, unused CSS versions, requirements cleanup, CKEditor 4.
