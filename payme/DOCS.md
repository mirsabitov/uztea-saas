# Payme Integration — UzTEA

## Umumiy ko'rinish

```
Foydalanuvchi → Order yaratiladi → payment_url → Payme Checkout
                                                        ↓
                              Backend ← JSON-RPC callbacks ← Payme
                                  ↓
                          Order status = paid
```

---

## .env sozlamalari

```env
PAYME_ENV=test                          # test | prod
PAYME_CASHBOX_ID=your_cashbox_id        # Payme merchant ID
PAYME_SECRET_KEY=your_secret_key        # Payme secret (Basic Auth parol)
PAYME_TEST_URL=https://checkout.test.paycom.uz
PAYME_PROD_URL=https://checkout.paycom.uz
```

---

## Webhook endpoint

```
POST /payments/payme/webhook/
```

**Authorization:**
```
Authorization: Basic base64("Paycom:<PAYME_SECRET_KEY>")
```

Payme portal da ro'yxatdan o'tishda ko'rsatiladi:
- **Endpoint URL:** `https://yourdomain.com/payments/payme/webhook/`
- **Account fields:**
  - `order_id` — integer (Order ID)
  - `user_id` — integer (Membership ID)

---

## Payment URL yaratish

```python
from payme.views import generate_payme_url

order = Order.objects.get(id=order_id)
url = generate_payme_url(order)
# → https://checkout.test.paycom.uz/bT1YWRj...
```

URL ichidagi parametrlar (decode qilinganda):
```
m=<cashbox_id>;ac.order_id=<order_id>;ac.user_id=<membership_id>;a=<amount_tiyin>
```

> **Eslatma:** `amount` tiyinda — 1 so'm = 100 tiyin.
> Masalan, 50 000 so'm → 5 000 000 tiyin.

---

## JSON-RPC Metodlar

### 1. CheckPerformTransaction

To'lov amalga oshirilishi mumkinligini tekshiradi.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "CheckPerformTransaction",
  "params": {
    "amount": 5000000,
    "account": {
      "order_id": 9,
      "user_id": 2
    }
  }
}
```

**Response (muvaffaqiyatli):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "allow": true
  }
}
```

**Xato holatlari:**

| Kod | Sabab |
|-----|-------|
| `-31050` | Order topilmadi yoki user_id mos kelmadi |
| `-31051` | Order allaqachon to'langan |
| `-31001` | Summa noto'g'ri |

---

### 2. CreateTransaction

Bazada tranzaksiya yaratadi.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "CreateTransaction",
  "params": {
    "id": "payme_transaction_id",
    "time": 1718123456789,
    "amount": 5000000,
    "account": {
      "order_id": 9,
      "user_id": 2
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "create_time": 1718123456789,
    "transaction": "1",
    "state": 1
  }
}
```

---

### 3. PerformTransaction

To'lovni yakunlaydi. Order `status = paid` bo'ladi.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "PerformTransaction",
  "params": {
    "id": "payme_transaction_id"
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "transaction": "1",
    "perform_time": 1718123500000,
    "state": 2
  }
}
```

---

### 4. CancelTransaction

To'lovni bekor qiladi. Order `status = failed` bo'ladi.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "CancelTransaction",
  "params": {
    "id": "payme_transaction_id",
    "reason": 1
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "transaction": "1",
    "cancel_time": 1718123600000,
    "state": -1
  }
}
```

**Bekor qilish sabablari (`reason`):**

| Kod | Ma'nosi |
|-----|---------|
| `1` | Foydalanuvchi bekor qildi |
| `2` | Tranzaksiya muddati tugadi |
| `3` | Order mavjud emas |
| `4` | To'lov amalga oshmadi |
| `5` | Noma'lum xato |

---

### 5. CheckTransaction

Tranzaksiya holatini tekshiradi.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "CheckTransaction",
  "params": {
    "id": "payme_transaction_id"
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "create_time": 1718123456789,
    "perform_time": 1718123500000,
    "cancel_time": 0,
    "transaction": "1",
    "state": 2,
    "reason": null
  }
}
```

---

### 6. GetStatement

Berilgan vaqt oralig'idagi barcha tranzaksiyalarni qaytaradi.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "GetStatement",
  "params": {
    "from": 1718100000000,
    "to": 1718200000000
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "result": {
    "transactions": [
      {
        "id": "payme_transaction_id",
        "time": 1718123456789,
        "amount": 5000000,
        "account": { "order_id": 9 },
        "create_time": 1718123456789,
        "perform_time": 1718123500000,
        "cancel_time": 0,
        "transaction": "1",
        "state": 2,
        "reason": null
      }
    ]
  }
}
```

---

## Tranzaksiya holatlari

| State | Ma'nosi |
|-------|---------|
| `1`  | Waiting — to'lov kutilmoqda |
| `2`  | Paid — to'landi |
| `-1` | Cancelled — to'lovdan oldin bekor |
| `-2` | Cancelled After — to'lovdan keyin qaytarildi |

---

## Order holatlari (bazada)

| Status | Ma'nosi |
|--------|---------|
| `pending` | To'lov boshlanmagan |
| `processing` | CreateTransaction chaqirildi |
| `paid` | PerformTransaction muvaffaqiyatli |
| `failed` | CancelTransaction chaqirildi |

---

## Modellar

### PaymeTransaction

| Field | Tur | Tavsif |
|-------|-----|--------|
| `transaction_id` | CharField | Payme tranzaksiya ID |
| `order` | ForeignKey | `click.Order` ga bog'liq |
| `amount` | Decimal | So'mda (tiyindan konvertatsiya qilingan) |
| `state` | SmallInteger | 1, 2, -1, -2 |
| `created_at` | DateTime | Yaratilgan vaqt |
| `performed_at` | DateTime | To'langan vaqt |
| `cancelled_at` | DateTime | Bekor qilingan vaqt |
| `reason` | SmallInteger | Bekor qilish sababi |

---

## curl bilan test qilish

```bash
AUTH=$(echo -n "Paycom:your_secret_key" | base64)

curl -X POST https://yourdomain.com/payments/payme/webhook/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $AUTH" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "CheckPerformTransaction",
    "params": {
      "amount": 5000000,
      "account": { "order_id": 9, "user_id": 2 }
    }
  }'
```
