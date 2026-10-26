# UzTEA Workspace — roadmap

One section at a time. A phase starts only after the previous one is reviewed and approved.
Decisions that are approved go into `CLAUDE.md`.

## Phase 1 — Interface and navigation · in review
Branch: `feature/uztea-workspace-ui` (not merged, not deployed).

Done:
- Staff-only `/workspace/` app with sidebar, header, the original logos and a shared style.
- People → Members: search (name, email, institution, membership ID), filters (type,
  position, language, institution type, country), sort, pagination, All members /
  Pending payment lists, column toggles, bulk actions (run by the admin), row → Member
  preview, full profile with 7 tabs that show every existing field.
- People → Teachers Bank and All contacts (every list, one row per record, "Also in" hints).
- Forms & Events: the three existing forms with real response counts, share link, export,
  templates; Form Studio as a sandbox (add, edit, duplicate, reorder, delete fields; preview).
- Payments: Orders, Pending Payments, ATMOS, Payme, Promo Codes, Click Tools (read-only).
- Partners list with search, filters, import/export, email action.
- Settings: branding, membership types and prices, users & groups, languages,
  integrations (configured / not configured only).
- More tools: every admin section the user may open, plus public pages.
- Payment status logic moved to `app/payment_status.py` (same rules as before) with tests.
- Demo data command for local checks.

Marked "Next phase" (not built): membership status and validity, Active / Renewal due,
card view, smart blocks, logic rules, saving / publishing forms, form settings, language
switch, editing organisation details.

## Phase 2 — People and the membership lifecycle · proposed next
Decide with the owner: what makes a membership active, how long it is valid (the welcome
email currently says 12 months from sending), renewal window, how payment results move a
member between states, and whether a separate Person record is needed.

## Phase 3 — Form Studio: build forms and collect responses
Form / Field / Submission models, draft → preview → publish → responses → archive,
versioning so edits don't break earlier answers.

## Phase 4 — Events: registration, capacity, attendees
Event model (date, place, capacity, deadline), link to forms, move TESOL / 30th
Anniversary in without changing their URLs or data.

## Phase 5 — Payments for new forms
Connect forms and events to the existing Click / Payme / Atmos flows without changing
their verification and callbacks.

## Phase 6 — Partners

## Phase 7 — Home and remaining Settings

## Found during Phase 1 (not changed)
- `/membership/<pk>/card/` is public and keyed by a sequential id, so anyone can open any
  member's card (name, contact details). Needs a token or login — to be decided.
- Items from the CLAUDE.md backlog (CSRF middleware off, `ALLOWED_HOSTS`, JWT lifetime,
  Redis URL, unused CSS versions, CKEditor 4) are still open.
