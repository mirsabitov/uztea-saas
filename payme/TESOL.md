# TESOL conference payments

- Registration: `/tesol/` (six required fields).
- Fee: **625,000 UZS**, fixed on the server in `app/conference.py`. Existing orders retain their original amounts.
- Checkout amount for new orders: **62,500,000 tiyin**. Payme's GET checkout format is documented at https://developer.help.paycom.uz/initsializatsiya-platezhey/otpravka-cheka-po-metodu-get/.
- Uses the existing merchant and `/payments/payme/webhook/` endpoint.
- `ac.order_id` identifies the shared Order record; `ac.user_id` is the conference registration ID for conference orders and the membership ID for membership orders.
- Registration and its order are saved in one database transaction. Conference orders do not create memberships or send membership welcome emails.
- The return page `/tesol/payment/<uuid>/` reads the order status from the database. Visiting it or adding query parameters never confirms payment. Keep this private payment link confidential.
- The admin TESOL registration list displays the current payment status.

## Deployment

Run `python manage.py migrate` and `python manage.py collectstatic --noinput` in the deployment environment, then restart the application. Include the new app and click migrations, plus the existing untracked initial/payment migrations required by this checkout.

Set `SITE_BASE_URL` to the chosen public HTTPS origin, configure its hostname in `ALLOWED_HOSTS` and its HTTPS origin in `CSRF_TRUSTED_ORIGINS`, and point the domain at the Django deployment. Verify that the existing Payme merchant callback reaches `/payments/payme/webhook/` on that deployment. A separate domain should use the same database as that callback.

Existing `PAYME_CASHBOX_ID`, `PAYME_SECRET_KEY` (or PaymeConfig), `PAYME_ENV`, and checkout URL settings are reused. Never use production checkout against the temporary local preview database. The automated tests simulate authenticated callbacks; they do not make a real payment or verify merchant-portal configuration.

The migration adding payment tokens assigns a separate UUID to each existing registration. Earlier registrations without an order remain visible as “No payment order”; no retrospective charge is created.
