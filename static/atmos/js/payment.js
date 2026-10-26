'use strict';

/* ─── Config ──────────────────────────────────────────────── */
const API = {
  start:   '/payments/atmos/api/start/',
  retryOtp:'/payments/atmos/api/retry-otp/',
  confirm: '/payments/atmos/api/confirm/',
};

const _params = new URLSearchParams(window.location.search);
const AMOUNT_TIYINS = parseInt(_params.get('amount')) || 500000;
const ACCOUNT_ID    = _params.get('order') || '';
const OTP_RESEND_COOLDOWN = 60; // seconds

/* ─── State ───────────────────────────────────────────────── */
let currentTransactionId = null;
let resendTimer = null;
let resendSeconds = 0;

/* ─── DOM refs ────────────────────────────────────────────── */
const screens = {
  payment: document.getElementById('screen-payment'),
  otp:     document.getElementById('screen-otp'),
  success: document.getElementById('screen-success'),
};

const cardNumInput  = document.getElementById('card-number');
const expiryInput   = document.getElementById('expiry');
const btnPay        = document.getElementById('btn-pay');

const otpDigits     = Array.from(document.querySelectorAll('.otp-digit'));
const btnConfirm    = document.getElementById('btn-confirm');
const btnBack       = document.getElementById('btn-back');
const btnResend     = document.getElementById('btn-resend');
const timerEl       = document.getElementById('resend-timer');

const btnNewPayment = document.getElementById('btn-new-payment');
const successTxnEl  = document.getElementById('success-txn-id');
const successAmtEl  = document.getElementById('success-amount');
const btnCopy       = document.getElementById('btn-copy-txn');

/* Visual card refs */
const bcNumber = document.getElementById('bc-number');
const bcExpiry = document.getElementById('bc-expiry');

/* ─── Display helpers ──────────────────────────────────────── */
function showScreen(name) {
  Object.entries(screens).forEach(([k, el]) => {
    el.classList.toggle('active', k === name);
  });
}

function formatMoney(tiyins) {
  const uzs = tiyins / 100;
  return new Intl.NumberFormat('uz-UZ').format(uzs);
}

/* ─── Toast ───────────────────────────────────────────────── */
const toastContainer = document.getElementById('toast-container');

const ICONS = {
  success: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:#22c55e"><polyline points="20 6 9 17 4 12"/></svg>`,
  error:   `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:#ef4444"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
  warning: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:#f59e0b"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
  info:    `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:#5b6af0"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
};

function toast(type, title, message = '', duration = 4500) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `
    <span class="toast-icon">${ICONS[type] || ICONS.info}</span>
    <div class="toast-body">
      <div class="toast-title">${title}</div>
      ${message ? `<div class="toast-msg">${message}</div>` : ''}
    </div>`;
  toastContainer.appendChild(el);

  setTimeout(() => {
    el.classList.add('fade-out');
    setTimeout(() => el.remove(), 280);
  }, duration);
}

/* ─── Card number formatting ──────────────────────────────── */
cardNumInput.addEventListener('input', (e) => {
  let v = e.target.value.replace(/\D/g, '').slice(0, 16);
  e.target.value = v.replace(/(.{4})/g, '$1 ').trim();
  clearFieldError(cardNumInput);

  const display = v.padEnd(16, '•');
  bcNumber.textContent = display.replace(/(.{4})/g, '$1 ').trim();
});

cardNumInput.addEventListener('keydown', (e) => {
  if (e.key === 'Backspace') {
    const v = e.target.value.replace(/\D/g, '');
    if (v.length === 0) bcNumber.textContent = '•••• •••• •••• ••••';
  }
});

/* ─── Expiry formatting ───────────────────────────────────── */
expiryInput.addEventListener('input', (e) => {
  let v = e.target.value.replace(/\D/g, '').slice(0, 4);
  if (v.length >= 3) v = v.slice(0, 2) + '/' + v.slice(2);
  e.target.value = v;
  clearFieldError(expiryInput);

  const raw = v.replace('/', '');
  if (raw.length === 4) {
    bcExpiry.textContent = v;
  } else if (raw.length >= 2) {
    bcExpiry.textContent = raw.slice(0, 2) + '/••';
  } else {
    bcExpiry.textContent = '••/••';
  }
});

/* ─── Validation ──────────────────────────────────────────── */
function showFieldError(input, message) {
  input.classList.add('error-field');
  const errEl = input.parentElement.querySelector('.field-error');
  if (errEl) { errEl.textContent = message; errEl.classList.add('visible'); }
}

function clearFieldError(input) {
  input.classList.remove('error-field');
  const errEl = input.parentElement.querySelector('.field-error');
  if (errEl) errEl.classList.remove('visible');
}

function validatePaymentForm() {
  let valid = true;
  const cardDigits = cardNumInput.value.replace(/\D/g, '');
  const expiryClean = expiryInput.value.replace('/', '');

  if (cardDigits.length !== 16) {
    showFieldError(cardNumInput, 'Enter a valid 16-digit card number');
    valid = false;
  }

  if (!/^\d{4}$/.test(expiryClean)) {
    showFieldError(expiryInput, 'Enter expiry as MM/YY');
    valid = false;
  } else {
    const month = parseInt(expiryClean.slice(0, 2), 10);
    if (month < 1 || month > 12) {
      showFieldError(expiryInput, 'Invalid month');
      valid = false;
    }
  }

  return valid;
}

/* ─── API helpers ─────────────────────────────────────────── */
async function apiPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!data.success) {
    const msg = data.error?.message || data.error || 'Unknown error';
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data;
}

function setLoading(btn, loading) {
  btn.disabled = loading;
  btn.classList.toggle('loading', loading);
}

/* ─── Payment flow ────────────────────────────────────────── */
btnPay.addEventListener('click', async () => {
  if (!validatePaymentForm()) return;

  const cardDigits = cardNumInput.value.replace(/\D/g, '');
  const expiry     = expiryInput.value.replace('/', '');

  setLoading(btnPay, true);

  try {
    const data = await apiPost(API.start, {
      amount:      AMOUNT_TIYINS,
      account:     ACCOUNT_ID || String(Date.now()),
      card_number: cardDigits,
      expiry:      expiry,
    });

    currentTransactionId = data.transaction_id;
    showScreen('otp');
    otpDigits[0].focus();
    startResendTimer();
    toast('info', 'OTP Sent', 'Enter the 6-digit code sent to your phone.');
  } catch (err) {
    toast('error', 'Payment Failed', err.message);
  } finally {
    setLoading(btnPay, false);
  }
});

/* ─── OTP input navigation ────────────────────────────────── */
otpDigits.forEach((input, idx) => {
  input.addEventListener('input', (e) => {
    const val = e.target.value.replace(/\D/g, '');
    e.target.value = val.slice(-1);
    e.target.classList.toggle('filled', !!e.target.value);
    if (val && idx < otpDigits.length - 1) otpDigits[idx + 1].focus();
    updateConfirmBtn();
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Backspace' && !input.value && idx > 0) {
      otpDigits[idx - 1].value = '';
      otpDigits[idx - 1].classList.remove('filled');
      otpDigits[idx - 1].focus();
      updateConfirmBtn();
    }
    if (e.key === 'ArrowLeft'  && idx > 0) otpDigits[idx - 1].focus();
    if (e.key === 'ArrowRight' && idx < otpDigits.length - 1) otpDigits[idx + 1].focus();
  });

  input.addEventListener('paste', (e) => {
    e.preventDefault();
    const pasted = (e.clipboardData || window.clipboardData).getData('text').replace(/\D/g, '');
    pasted.split('').slice(0, otpDigits.length).forEach((ch, i) => {
      if (otpDigits[i]) { otpDigits[i].value = ch; otpDigits[i].classList.add('filled'); }
    });
    const next = Math.min(pasted.length, otpDigits.length - 1);
    otpDigits[next].focus();
    updateConfirmBtn();
  });
});

function getOtpValue() {
  return otpDigits.map(d => d.value).join('');
}

function updateConfirmBtn() {
  btnConfirm.disabled = getOtpValue().length !== 6;
}

function clearOtp() {
  otpDigits.forEach(d => { d.value = ''; d.classList.remove('filled'); });
  updateConfirmBtn();
}

updateConfirmBtn();

/* ─── Confirm OTP ──────────────────────────────────────────── */
btnConfirm.addEventListener('click', async () => {
  const otp = getOtpValue();
  if (otp.length !== 6) return;

  setLoading(btnConfirm, true);

  try {
    const data = await apiPost(API.confirm, {
      transaction_id: currentTransactionId,
      otp,
    });

    clearResendTimer();
    showSuccessScreen(data);
    toast('success', 'Payment Successful', 'Your transaction has been completed.');
  } catch (err) {
    toast('error', 'Verification Failed', err.message);
    clearOtp();
    otpDigits[0].focus();
  } finally {
    setLoading(btnConfirm, false);
  }
});

/* ─── Back button ──────────────────────────────────────────── */
btnBack.addEventListener('click', () => {
  clearResendTimer();
  clearOtp();
  showScreen('payment');
});

/* ─── Resend timer ─────────────────────────────────────────── */
function startResendTimer() {
  resendSeconds = OTP_RESEND_COOLDOWN;
  btnResend.disabled = true;
  tickTimer();
  resendTimer = setInterval(tickTimer, 1000);
}

function tickTimer() {
  timerEl.textContent = resendSeconds > 0 ? `(${resendSeconds}s)` : '';
  if (resendSeconds <= 0) {
    clearResendTimer();
    btnResend.disabled = false;
  }
  resendSeconds--;
}

function clearResendTimer() {
  clearInterval(resendTimer);
  timerEl.textContent = '';
}

btnResend.addEventListener('click', async () => {
  if (!currentTransactionId) return;
  btnResend.disabled = true;

  try {
    await apiPost(API.retryOtp, {
      transaction_id: currentTransactionId,
    });
    toast('info', 'OTP Resent', 'A new code has been sent to your phone.');
    clearOtp();
    startResendTimer();
    otpDigits[0].focus();
  } catch (err) {
    toast('warning', 'Resend Failed', err.message);
    btnResend.disabled = false;
  }
});

/* ─── Success screen ───────────────────────────────────────── */
function showSuccessScreen(data) {
  showScreen('success');

  const txnId  = data.transaction_id || currentTransactionId || '—';
  const amount = data.amount_uzs
    ? `${new Intl.NumberFormat('uz-UZ').format(data.amount_uzs)} UZS`
    : `${formatMoney(AMOUNT_TIYINS)} UZS`;

  successTxnEl.textContent = txnId;
  successAmtEl.textContent = amount;

  btnCopy.dataset.txn = txnId;
}

/* ─── Copy transaction ID ──────────────────────────────────── */
btnCopy.addEventListener('click', async () => {
  const txn = btnCopy.dataset.txn || successTxnEl.textContent;
  try {
    await navigator.clipboard.writeText(txn);
    btnCopy.classList.add('copied');
    btnCopy.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
    setTimeout(() => {
      btnCopy.classList.remove('copied');
      btnCopy.innerHTML = COPY_ICON;
    }, 2000);
  } catch {
    toast('warning', 'Copy failed', 'Please copy manually.');
  }
});

const COPY_ICON = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;

/* ─── New payment button ───────────────────────────────────── */
btnNewPayment.addEventListener('click', () => {
  currentTransactionId = null;
  clearOtp();
  const TEST_CARD = '9860090101014364';
  cardNumInput.value   = TEST_CARD.replace(/(.{4})/g, '$1 ').trim();
  expiryInput.value    = '02/28';
  bcNumber.textContent = TEST_CARD.replace(/(.{4})/g, '$1 ').trim();
  bcExpiry.textContent = '02/28';
  clearFieldError(cardNumInput);
  clearFieldError(expiryInput);
  showScreen('payment');
});

/* ─── Init ─────────────────────────────────────────────────── */
document.getElementById('amount-display').textContent =
  `${formatMoney(AMOUNT_TIYINS)} UZS`;

/* ─── Sandbox test-card pre-fill ───────────────────────────── */
(function prefillTestCard() {
  const TEST_CARD   = '9860090101014364';
  const TEST_EXPIRY = '02/28';

  cardNumInput.value = TEST_CARD.replace(/(.{4})/g, '$1 ').trim();
  expiryInput.value  = TEST_EXPIRY;

  bcNumber.textContent = TEST_CARD.replace(/(.{4})/g, '$1 ').trim();
  bcExpiry.textContent  = TEST_EXPIRY;
})();

/* ─── OTP hint: click to auto-fill 111111 ──────────────────── */
document.querySelector('.otp-sandbox-hint')?.addEventListener('click', () => {
  '111111'.split('').forEach((ch, i) => {
    otpDigits[i].value = ch;
    otpDigits[i].classList.add('filled');
  });
  updateConfirmBtn();
  toast('info', 'OTP filled', 'Test OTP 111111 inserted.');
});
