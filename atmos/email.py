import logging
from email.mime.image import MIMEImage

from django.core.mail import EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger('atmos')


LOGO_CONTENT_ID = 'uztea-logo'


def _logo_bytes() -> bytes:
    paths = [
        settings.BASE_DIR / 'staticfiles' / 'images' / 'uztea.png',
        settings.BASE_DIR / 'static' / 'images' / 'uztea.png',
        settings.BASE_DIR / 'app' / 'static' / 'images' / 'uztea.png',
        settings.BASE_DIR / 'app' / 'static' / 'app' / 'images' / 'uztea.png',
    ]
    for path in paths:
        try:
            with open(path, 'rb') as f:
                return f.read()
        except OSError:
            continue
    return b''



def send_fiscal_receipt(email: str, full_name: str, amount_uzs: float,
                         ofd_url: str, order_id: str, membership_type: str = ''):
    subject = 'UzTEA — Payment Confirmation & Fiscal Receipt'
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@uztea.uz')

    amount_formatted = f"{amount_uzs:,.0f} UZS"
    logo_bytes = _logo_bytes()
    logo_tag = (
        f'<table width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td align="center" style="padding-bottom:10px;">'
        f'<img src="cid:{LOGO_CONTENT_ID}" alt="UzTEA" '
        f'width="80" style="display:block;border:0;" /></td></tr></table>'
    ) if logo_bytes else ''

    membership_row = f"""
                <tr>
                  <td style="padding:12px 0;border-bottom:1px solid #e8edf5;
                             font-size:13px;color:#5a6a8a;font-family:Arial,sans-serif;">
                    Membership Type
                  </td>
                  <td style="padding:12px 0;border-bottom:1px solid #e8edf5;
                             font-size:13px;font-weight:700;color:#0a1a3a;
                             text-align:right;font-family:Arial,sans-serif;">
                    {membership_type}
                  </td>
                </tr>""" if membership_type else ''

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Payment Confirmation</title>
</head>
<body style="margin:0;padding:0;background:#eef2f8;font-family:Arial,'Helvetica Neue',sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f8;padding:40px 0;">
  <tr>
    <td align="center">

      <!-- Card -->
      <table width="580" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:4px;overflow:hidden;
                    box-shadow:0 2px 12px rgba(2,72,144,0.10);">

        <!-- Header -->
        <tr>
          <td style="background:#024890;padding:0;">
            <!-- Gold top border -->
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr><td style="height:4px;background:#f5b706;"></td></tr>
              <tr>
                <td style="padding:28px 40px 24px;text-align:center;">
                  {logo_tag}
                  <div style="font-size:22px;font-weight:700;color:#ffffff;
                              letter-spacing:1px;font-family:Arial,sans-serif;">
                    UzTEA
                  </div>
                  <div style="font-size:11px;color:rgba(255,255,255,0.7);
                              margin-top:4px;letter-spacing:.5px;
                              font-family:Arial,sans-serif;">
                    UZBEKISTAN TEACHERS OF ENGLISH ASSOCIATION
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Status bar -->
        <tr>
          <td style="background:#f5b706;padding:10px 40px;text-align:center;">
            <span style="font-size:12px;font-weight:700;color:#024890;
                         letter-spacing:1.5px;font-family:Arial,sans-serif;">
              PAYMENT CONFIRMED
            </span>
          </td>
        </tr>

        <!-- Greeting -->
        <tr>
          <td style="padding:32px 40px 0;text-align:center;">
            <p style="margin:0;font-size:15px;color:#0a1a3a;
                      font-family:Arial,sans-serif;line-height:1.6;">
              Dear <strong>{full_name}</strong>,
            </p>
            <p style="margin:10px 0 0;font-size:13px;color:#5a6a8a;
                      font-family:Arial,sans-serif;line-height:1.7;">
              Your membership payment has been successfully processed.
              Please find your payment details and official fiscal receipt below.
            </p>
          </td>
        </tr>

        <!-- Divider -->
        <tr>
          <td style="padding:24px 40px 0;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr><td style="height:1px;background:#e2e8f0;"></td></tr>
            </table>
          </td>
        </tr>

        <!-- Section title -->
        <tr>
          <td style="padding:20px 40px 0;text-align:center;">
            <p style="margin:0;font-size:10px;font-weight:700;color:#024890;
                      letter-spacing:2px;font-family:Arial,sans-serif;">
              PAYMENT DETAILS
            </p>
          </td>
        </tr>

        <!-- Details table -->
        <tr>
          <td style="padding:12px 40px 0;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:12px 0;border-bottom:1px solid #e8edf5;
                           font-size:13px;color:#5a6a8a;font-family:Arial,sans-serif;">
                  Member Name
                </td>
                <td style="padding:12px 0;border-bottom:1px solid #e8edf5;
                           font-size:13px;font-weight:700;color:#0a1a3a;
                           text-align:right;font-family:Arial,sans-serif;">
                  {full_name}
                </td>
              </tr>
              <tr>
                <td style="padding:12px 0;border-bottom:1px solid #e8edf5;
                           font-size:13px;color:#5a6a8a;font-family:Arial,sans-serif;">
                  ID
                </td>
                <td style="padding:12px 0;border-bottom:1px solid #e8edf5;
                           font-size:13px;font-weight:700;color:#024890;
                           text-align:right;font-family:Arial,sans-serif;">
                  UZ{int(order_id):06d}
                </td>
              </tr>
              <tr>
                <td style="padding:12px 0;border-bottom:1px solid #e8edf5;
                           font-size:13px;color:#5a6a8a;font-family:Arial,sans-serif;">
                  Order Reference
                </td>
                <td style="padding:12px 0;border-bottom:1px solid #e8edf5;
                           font-size:13px;font-weight:700;color:#0a1a3a;
                           text-align:right;font-family:Arial,sans-serif;">
                  #{order_id}
                </td>
              </tr>
              {membership_row}
              <tr>
                <td style="padding:14px 0;font-size:13px;color:#5a6a8a;
                           font-family:Arial,sans-serif;">
                  Amount Paid
                </td>
                <td style="padding:14px 0;text-align:right;">
                  <span style="font-size:16px;font-weight:700;color:#024890;
                               font-family:Arial,sans-serif;">
                    {amount_formatted}
                  </span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Divider -->
        <tr>
          <td style="padding:8px 40px 0;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr><td style="height:1px;background:#e2e8f0;"></td></tr>
            </table>
          </td>
        </tr>

        <!-- Fiscal receipt -->
        <tr>
          <td style="padding:24px 40px;text-align:center;">
            <p style="margin:0 0 6px;font-size:10px;font-weight:700;color:#024890;
                      letter-spacing:2px;font-family:Arial,sans-serif;">
              OFFICIAL FISCAL RECEIPT
            </p>
            <p style="margin:0 0 18px;font-size:12px;color:#5a6a8a;
                      font-family:Arial,sans-serif;line-height:1.6;">
              Your official fiscal receipt (fiskal chek) has been issued
              in accordance with Uzbekistan tax regulations.
            </p>
            <table cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;">
              <tr>
                <td style="background:#024890;border-radius:3px;">
                  <a href="{ofd_url}"
                     style="display:inline-block;padding:12px 28px;
                            font-size:13px;font-weight:700;color:#ffffff;
                            text-decoration:none;letter-spacing:.5px;
                            font-family:Arial,sans-serif;">
                    VIEW FISCAL RECEIPT
                  </a>
                </td>
              </tr>
            </table>
            <p style="margin:14px 0 0;font-size:11px;color:#8a9ab8;
                      font-family:Arial,sans-serif;word-break:break-all;text-align:center;">
              {ofd_url}
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f7f9fc;border-top:1px solid #e2e8f0;
                     padding:16px 40px;text-align:center;">
            <p style="margin:0;font-size:11px;color:#8a9ab8;
                      font-family:Arial,sans-serif;line-height:1.7;">
              &copy; UzTEA &nbsp;|&nbsp;
              <a href="https://uztea.uz" style="color:#024890;text-decoration:none;">uztea.uz</a>
              &nbsp;|&nbsp;
              <a href="mailto:info@uztea.uz" style="color:#024890;text-decoration:none;">info@uztea.uz</a>
            </p>
          </td>
        </tr>

        <!-- Bottom gold border -->
        <tr><td style="height:4px;background:#f5b706;"></td></tr>

      </table>

    </td>
  </tr>
</table>

</body>
</html>"""

    text = (
        f"UzTEA — Payment Confirmed\n\n"
        f"Dear {full_name},\n\n"
        f"Your payment of {amount_formatted} has been successfully processed.\n"
        f"Order Reference: #{order_id}\n"
        f"{'Membership: ' + membership_type + chr(10) if membership_type else ''}\n"
        f"Official Fiscal Receipt:\n{ofd_url}\n\n"
        f"UzTEA — uztea.uz"
    )

    try:
        msg = EmailMultiAlternatives(subject, text, from_email, [email])
        msg.attach_alternative(html, 'text/html')
        if logo_bytes:
            msg.mixed_subtype = 'related'
            logo = MIMEImage(logo_bytes, _subtype='png')
            logo.add_header('Content-ID', f'<{LOGO_CONTENT_ID}>')
            logo.add_header('Content-Disposition', 'inline', filename='uztea.png')
            msg.attach(logo)
        msg.send()
        logger.info('fiscal_receipt | sent to %s | order=%s', email, order_id)
    except Exception as exc:
        logger.error('fiscal_receipt | failed to send to %s: %s', email, exc)


def send_welcome_email(email: str, full_name: str, membership_id: str,
                       membership_type: str, expiry_date: str):
    subject = 'Welcome to UzTEA – Your Membership is Now Active'
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@uztea.uz')
    logo_bytes = _logo_bytes()
    logo_tag = (
        f'<table width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td align="center" style="padding-bottom:10px;">'
        f'<img src="cid:{LOGO_CONTENT_ID}" alt="UzTEA" '
        f'width="80" style="display:block;border:0;" /></td></tr></table>'
    ) if logo_bytes else ''

    benefits = [
        'Professional development webinars, workshops, and conferences',
        'Selected member-only resources and publications',
        'Networking opportunities with educators and institutions',
        'Discounted or free participation for UzTEA events and partner activities',
        'Opportunities to participate in UzTEA committees, SIGs, and projects',
        'Scholarship, training, and international collaboration opportunities',
        'Exclusive offers from UzTEA partners and educational organizations',
        'Access to selected recordings, materials, and CPD resources',
    ]
    dashboard = [
        'Manage your membership profile and contact information',
        'Access member resources and event materials',
        'Register for upcoming events and webinars',
        'Track your participation and certificates',
        'Manage communication preferences',
        'View membership status and renewal information',
    ]

    def _list(items):
        rows = ''
        for it in items:
            rows += (
                '<tr><td style="padding:5px 0;font-size:13px;color:#334155;'
                'font-family:Arial,sans-serif;line-height:1.5;vertical-align:top;">'
                '<span style="color:#f5b706;font-weight:900;">&bull;</span>&nbsp;&nbsp;'
                f'{it}</td></tr>'
            )
        return rows

    socials = [
        ('Telegram', 'https://t.me/uzteauz'),
        ('Instagram', 'https://www.instagram.com/uztea.uz'),
        ('YouTube', 'https://www.youtube.com/@UzTEA'),
        ('LinkedIn', 'https://www.linkedin.com/company/uztea'),
        ('Facebook', 'https://www.facebook.com/uztea'),
    ]
    social_links = ' &nbsp;|&nbsp; '.join(
        f'<a href="{url}" style="color:#024890;text-decoration:none;font-weight:700;">{name}</a>'
        for name, url in socials
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Welcome to UzTEA</title></head>
<body style="margin:0;padding:0;background:#eef2f8;font-family:Arial,'Helvetica Neue',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f8;padding:40px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:4px;overflow:hidden;box-shadow:0 2px 12px rgba(2,72,144,0.10);">

      <!-- Header -->
      <tr><td style="background:#024890;padding:0;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr><td style="height:4px;background:#f5b706;"></td></tr>
          <tr><td style="padding:28px 40px 24px;text-align:center;">
            {logo_tag}
            <div style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:1px;">UzTEA</div>
            <div style="font-size:11px;color:rgba(255,255,255,0.7);margin-top:4px;letter-spacing:.5px;">UZBEKISTAN TEACHERS OF ENGLISH ASSOCIATION</div>
          </td></tr>
        </table>
      </td></tr>

      <!-- Status bar -->
      <tr><td style="background:#f5b706;padding:10px 40px;text-align:center;">
        <span style="font-size:12px;font-weight:700;color:#024890;letter-spacing:1.5px;">MEMBERSHIP ACTIVE</span>
      </td></tr>

      <!-- Greeting -->
      <tr><td style="padding:32px 40px 0;text-align:center;">
        <h1 style="margin:0 0 6px;font-size:22px;font-weight:700;color:#0a1a3a;">Welcome to UzTEA!</h1>
        <p style="margin:0;font-size:14px;color:#334155;line-height:1.6;">Hi <strong>{full_name}</strong>,</p>
        <p style="margin:12px 0 0;font-size:13px;color:#5a6a8a;line-height:1.7;">
          We are delighted to welcome you to the Uzbekistan Teachers of English Association (UzTEA)
          — a growing professional community connecting English language educators, researchers,
          institutions, and education leaders across Uzbekistan and internationally.
        </p>
      </td></tr>

      <!-- Membership details -->
      <tr><td style="padding:26px 40px 0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8faff;border:1.5px solid #e2e8f0;border-radius:10px;">
          <tr><td style="padding:16px 20px 6px;">
            <span style="font-size:10px;font-weight:700;color:#024890;letter-spacing:2px;">YOUR MEMBERSHIP DETAILS</span>
          </td></tr>
          <tr><td style="padding:6px 20px 16px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #e8edf5;font-size:13px;color:#5a6a8a;">Membership ID</td>
                <td style="padding:8px 0;border-bottom:1px solid #e8edf5;font-size:13px;font-weight:700;color:#024890;text-align:right;">{membership_id}</td>
              </tr>
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #e8edf5;font-size:13px;color:#5a6a8a;">Membership Type</td>
                <td style="padding:8px 0;border-bottom:1px solid #e8edf5;font-size:13px;font-weight:700;color:#0a1a3a;text-align:right;">{membership_type}</td>
              </tr>
              <tr>
                <td style="padding:8px 0;font-size:13px;color:#5a6a8a;">Expiry Date</td>
                <td style="padding:8px 0;font-size:13px;font-weight:700;color:#0a1a3a;text-align:right;">{expiry_date}</td>
              </tr>
            </table>
          </td></tr>
        </table>
      </td></tr>

      <!-- Benefits -->
      <tr><td style="padding:26px 40px 0;">
        <p style="margin:0 0 4px;font-size:15px;font-weight:700;color:#0a1a3a;">What do I receive as part of my membership?</p>
        <p style="margin:0 0 10px;font-size:12.5px;color:#5a6a8a;">As a UzTEA member, you will receive access to:</p>
        <table width="100%" cellpadding="0" cellspacing="0">{_list(benefits)}</table>
      </td></tr>

      <!-- Dashboard -->
      <tr><td style="padding:24px 40px 0;">
        <p style="margin:0 0 4px;font-size:15px;font-weight:700;color:#0a1a3a;">My Dashboard</p>
        <p style="margin:0 0 10px;font-size:12.5px;color:#5a6a8a;">Using your registered email and password, you may access your member dashboard to:</p>
        <table width="100%" cellpadding="0" cellspacing="0">{_list(dashboard)}</table>
        <p style="margin:12px 0 0;font-size:12px;color:#b45309;background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:10px 12px;line-height:1.5;">
          <strong>Note:</strong> This service will be available very soon. We will notify you with all procedures.
        </p>
      </td></tr>

      <!-- About -->
      <tr><td style="padding:24px 40px 0;">
        <p style="margin:0 0 4px;font-size:15px;font-weight:700;color:#0a1a3a;">About UzTEA</p>
        <p style="margin:0;font-size:13px;color:#5a6a8a;line-height:1.7;">
          As an official Associate Member of IATEFL (UK), UzTEA supports the professional growth of English
          language educators in Uzbekistan by connecting local teachers with international ELT expertise,
          global partnerships, and professional opportunities.
        </p>
      </td></tr>

      <!-- Social -->
      <tr><td style="padding:22px 40px 0;text-align:center;">
        <p style="margin:0 0 10px;font-size:13px;color:#5a6a8a;line-height:1.6;">Follow UzTEA to stay updated on events, scholarships, webinars, and community activities:</p>
        <p style="margin:0;font-size:13px;">{social_links}</p>
      </td></tr>

      <!-- Contact -->
      <tr><td style="padding:24px 40px 0;text-align:center;">
        <p style="margin:0 0 4px;font-size:14px;font-weight:700;color:#0a1a3a;">Questions about your membership?</p>
        <p style="margin:0;font-size:13px;color:#5a6a8a;line-height:1.7;">
          <a href="mailto:info@uztea.uz" style="color:#024890;text-decoration:none;font-weight:700;">info@uztea.uz</a>
          &nbsp;&middot;&nbsp;
          <a href="https://uztea.uz" style="color:#024890;text-decoration:none;font-weight:700;">www.uztea.uz</a>
        </p>
      </td></tr>

      <!-- Closing -->
      <tr><td style="padding:24px 40px 30px;text-align:center;">
        <p style="margin:0;font-size:13px;color:#5a6a8a;line-height:1.7;">
          Thank you for joining the UzTEA community. We look forward to your active participation and
          contribution to the development of English Language Teaching in Uzbekistan.
        </p>
        <p style="margin:16px 0 0;font-size:13px;color:#0a1a3a;line-height:1.6;">
          Yours sincerely,<br>
          <strong>UzTEA Membership Support</strong><br>
          <span style="color:#5a6a8a;">Uzbekistan Teachers of English Association</span>
        </p>
      </td></tr>

      <!-- Footer -->
      <tr><td style="background:#f7f9fc;border-top:1px solid #e2e8f0;padding:16px 40px;text-align:center;">
        <p style="margin:0;font-size:11px;color:#8a9ab8;line-height:1.7;">
          &copy; UzTEA &nbsp;|&nbsp;
          <a href="https://uztea.uz" style="color:#024890;text-decoration:none;">uztea.uz</a> &nbsp;|&nbsp;
          <a href="mailto:info@uztea.uz" style="color:#024890;text-decoration:none;">info@uztea.uz</a>
        </p>
      </td></tr>
      <tr><td style="height:4px;background:#f5b706;"></td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

    text = (
        f"Welcome to UzTEA – Your Membership is Now Active\n\n"
        f"Hi {full_name},\n\n"
        f"Welcome to the Uzbekistan Teachers of English Association (UzTEA).\n\n"
        f"Your Membership Details:\n"
        f"  Membership ID: {membership_id}\n"
        f"  Membership Type: {membership_type}\n"
        f"  Expiry Date: {expiry_date}\n\n"
        f"Questions? info@uztea.uz | www.uztea.uz\n\n"
        f"Yours sincerely,\nUzTEA Membership Support"
    )

    try:
        msg = EmailMultiAlternatives(subject, text, from_email, [email])
        msg.attach_alternative(html, 'text/html')
        if logo_bytes:
            msg.mixed_subtype = 'related'
            logo = MIMEImage(logo_bytes, _subtype='png')
            logo.add_header('Content-ID', f'<{LOGO_CONTENT_ID}>')
            logo.add_header('Content-Disposition', 'inline', filename='uztea.png')
            msg.attach(logo)
        msg.send()
        logger.info('welcome_email | sent to %s | id=%s', email, membership_id)
        return True
    except Exception as exc:
        logger.error('welcome_email | failed to send to %s: %s', email, exc)
        return False


def send_member_card_email(email: str, full_name: str, card_url: str,
                           membership_id: str, institution_name: str = ''):
    subject = 'Your UzTEA Membership Card is Ready'
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@uztea.uz')
    logo_bytes = _logo_bytes()
    logo_tag = (
        f'<table width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td align="center" style="padding-bottom:10px;">'
        f'<img src="cid:{LOGO_CONTENT_ID}" alt="UzTEA" '
        f'width="80" style="display:block;border:0;" /></td></tr></table>'
    ) if logo_bytes else ''

    inst_row = (
        f'<tr><td style="padding:8px 0;border-bottom:1px solid #e8edf5;font-size:13px;color:#5a6a8a;">Institution</td>'
        f'<td style="padding:8px 0;border-bottom:1px solid #e8edf5;font-size:13px;font-weight:700;color:#0a1a3a;text-align:right;">{institution_name}</td></tr>'
    ) if institution_name else ''

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Your UzTEA Membership Card</title></head>
<body style="margin:0;padding:0;background:#eef2f8;font-family:Arial,'Helvetica Neue',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f8;padding:40px 0;">
  <tr><td align="center">
    <table width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:4px;overflow:hidden;box-shadow:0 2px 12px rgba(2,72,144,0.10);">

      <tr><td style="background:#024890;padding:0;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr><td style="height:4px;background:#f5b706;"></td></tr>
          <tr><td style="padding:28px 40px 24px;text-align:center;">
            {logo_tag}
            <div style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:1px;">UzTEA</div>
            <div style="font-size:11px;color:rgba(255,255,255,0.7);margin-top:4px;letter-spacing:.5px;">UZBEKISTAN TEACHERS OF ENGLISH ASSOCIATION</div>
          </td></tr>
        </table>
      </td></tr>

      <tr><td style="background:#f5b706;padding:10px 40px;text-align:center;">
        <span style="font-size:12px;font-weight:700;color:#024890;letter-spacing:1.5px;">MEMBERSHIP CARD READY</span>
      </td></tr>

      <tr><td style="padding:32px 40px 0;text-align:center;">
        <h1 style="margin:0 0 6px;font-size:22px;font-weight:700;color:#0a1a3a;">Welcome to UzTEA!</h1>
        <p style="margin:0;font-size:14px;color:#334155;line-height:1.6;">Hi <strong>{full_name}</strong>,</p>
        <p style="margin:12px 0 0;font-size:13px;color:#5a6a8a;line-height:1.7;">
          You have been included as a member under your institution's UzTEA membership.
          Your personal digital membership card is now ready.
        </p>
      </td></tr>

      <tr><td style="padding:24px 40px 0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8faff;border:1.5px solid #e2e8f0;border-radius:10px;">
          <tr><td style="padding:14px 20px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr><td style="padding:8px 0;border-bottom:1px solid #e8edf5;font-size:13px;color:#5a6a8a;">Member Name</td>
                  <td style="padding:8px 0;border-bottom:1px solid #e8edf5;font-size:13px;font-weight:700;color:#0a1a3a;text-align:right;">{full_name}</td></tr>
              <tr><td style="padding:8px 0;{'border-bottom:1px solid #e8edf5;' if inst_row else ''}font-size:13px;color:#5a6a8a;">Membership ID</td>
                  <td style="padding:8px 0;{'border-bottom:1px solid #e8edf5;' if inst_row else ''}font-size:13px;font-weight:700;color:#024890;text-align:right;">{membership_id}</td></tr>
              {inst_row}
            </table>
          </td></tr>
        </table>
      </td></tr>

      <tr><td style="padding:26px 40px;text-align:center;">
        <p style="margin:0 0 16px;font-size:13px;color:#5a6a8a;line-height:1.6;">View, save, or print your official membership card:</p>
        <table cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;">
          <tr><td style="background:#024890;border-radius:3px;">
            <a href="{card_url}" style="display:inline-block;padding:13px 30px;font-size:13px;font-weight:700;color:#ffffff;text-decoration:none;letter-spacing:.5px;">VIEW MY MEMBERSHIP CARD</a>
          </td></tr>
        </table>
        <p style="margin:14px 0 0;font-size:11px;color:#8a9ab8;word-break:break-all;">{card_url}</p>
      </td></tr>

      <tr><td style="background:#f7f9fc;border-top:1px solid #e2e8f0;padding:16px 40px;text-align:center;">
        <p style="margin:0;font-size:11px;color:#8a9ab8;line-height:1.7;">
          &copy; UzTEA &nbsp;|&nbsp;
          <a href="https://uztea.uz" style="color:#024890;text-decoration:none;">uztea.uz</a> &nbsp;|&nbsp;
          <a href="mailto:info@uztea.uz" style="color:#024890;text-decoration:none;">info@uztea.uz</a>
        </p>
      </td></tr>
      <tr><td style="height:4px;background:#f5b706;"></td></tr>

    </table>
  </td></tr>
</table>
</body></html>"""

    text = (
        f"Your UzTEA Membership Card is Ready\n\n"
        f"Hi {full_name},\n\n"
        f"You have been included as a member under your institution's UzTEA membership.\n"
        f"Membership ID: {membership_id}\n\n"
        f"View your membership card:\n{card_url}\n\n"
        f"UzTEA — uztea.uz"
    )

    try:
        msg = EmailMultiAlternatives(subject, text, from_email, [email])
        msg.attach_alternative(html, 'text/html')
        if logo_bytes:
            msg.mixed_subtype = 'related'
            logo = MIMEImage(logo_bytes, _subtype='png')
            logo.add_header('Content-ID', f'<{LOGO_CONTENT_ID}>')
            logo.add_header('Content-Disposition', 'inline', filename='uztea.png')
            msg.attach(logo)
        msg.send()
        logger.info('member_card_email | sent to %s | id=%s', email, membership_id)
    except Exception as exc:
        logger.error('member_card_email | failed to send to %s: %s', email, exc)
