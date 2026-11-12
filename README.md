# By Direct – Backend API

E-commerce REST API built for an Industrial Training project.
**Stack:** FastAPI · SQLAlchemy 2 (async) · MySQL · Redis · Celery · Stripe · Paystack · Cloudinary · JWT.

## Features

| Area | What it does |
|------|--------------|
| Auth | Register with email verification, login, refresh-token rotation, logout (token blacklist), change password, forgot password with a one-time code (OTP) |
| Users | Profile, addresses, admin user management, roles `customer` / `admin` / `superadmin` |
| Products & categories | CRUD, search, filters, pagination, multiple images, signed direct uploads to Cloudinary |
| Cart & wishlist | Logged-in users, and **guests** (identified by the `X-Guest-Id` header); merged into the account after login |
| Orders | Checkout with stock reservation, idempotency key, order state machine, automatic expiry of unpaid orders |
| Payments | Stripe (PaymentIntent) and Paystack (popup access code), signed webhooks, amount check, replay protection |
| Reviews | Customers review products they bought |
| Analytics | Admin dashboard figures |
| Background jobs | Celery worker + beat: emails, order expiry |

## Project layout

```
app/
  core/         config, database, security (JWT, hashing), redis, enums, exceptions
  domains/      one folder per feature: route -> service -> repository -> schema
                (auth, user, product, category, cart, wishlist, order, payment, review, webhook, analytics)
  models/       SQLAlchemy tables
  middleware/   request logging
  email_server/ email templates + sender
  workers/      Celery app and tasks
alembic/        database migrations
tests/          pytest suite (auth, payment, order, guest)
```

Request flow: **route** (HTTP) → **service** (business rules) → **repository** (database) → **model**.

## Requirements

* Python 3.12+
* MySQL 8 and Redis (or just Docker)
* Accounts/keys for: SMTP (Gmail app password), Stripe, Paystack, Cloudinary (free plan is enough)

## Setup (without Docker)

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # then fill in the values (see below)
alembic upgrade head                # create the tables
uvicorn app.main:app --reload --port 8000
```

In two more terminals (needed for emails and for cancelling unpaid orders):

```bash
celery -A app.workers.celery_config:celery_app worker --loglevel=INFO
celery -A app.workers.celery_config:celery_app beat   --loglevel=INFO
```

Interactive docs: <http://localhost:8000/docs>

## Setup (Docker)

```bash
cp .env.example .env
docker compose up --build
```

Starts MySQL, Redis, runs the migrations, then the API (port 8000), the Celery worker and Celery beat.
Run the tests in Docker with `docker compose run --rm pytest`.

## Environment variables (`.env`)

| Variable | Meaning |
|----------|---------|
| `DEBUG` | `True` / `False` |
| `DATABASE_URL` | e.g. `mysql+asyncmy://user:pass@localhost:3306/by_direct_db` |
| `REDIS_URL` | e.g. `redis://localhost:6379/0` |
| `TEST_DATABASE_URL`, `TEST_REDIS_URL` | used only by pytest (SQLite file + Redis DB 15) |
| `SECRET_KEY` | long random string used to sign JWTs |
| `SUPERADMIN_*` | email, names, phone and password of the first admin (created on start-up) |
| `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS` | email sending (Gmail: use an *app password*) |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Stripe |
| `PAYSTACK_SECRET_KEY` | Paystack (also used to verify webhook signatures) |
| `ALLOWED_ORIGINS` | JSON list of frontend URLs allowed by CORS, e.g. `["http://localhost:5500"]` |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, `CLOUDINARY_UPLOAD_FOLDER` | image storage |
| `FRONTEND_URL` (optional) | where the email links send the user |

Never commit `.env`. Secrets stay on the server; the frontend only ever receives the Stripe *publishable* key.

## Validation rules (what the API accepts)

* **Password:** 8+ characters with a lowercase letter, an uppercase letter, a digit and one of `+ _ @ ,` or `-`. Example: `Passw0rd@123`
* **Names:** letters only, 2–100 characters
* **Phone:** Nigerian number, e.g. `07014719399` or `+2347014719399`
* **OTP (reset code):** 64 characters (hex), taken from the email
* **Checkout:** `X-Idempotency-Key` header required; country is a 2-letter code (`NG`)
* **Price:** at most 8 digits with 2 decimals

## API overview (`/api/v1`)

| Prefix | Examples |
|--------|----------|
| `/auth` | `POST /register`, `GET /verify-email`, `POST /login`, `POST /refresh`, `POST /logout`, `PATCH /password`, `POST /forget-password`, `POST /verify-otp`, `POST /reset-password` |
| `/users` | profile, addresses, admin user list |
| `/products`, `/categories` | list/search, detail, admin create/update/delete, `GET /products/upload-signature` |
| `/carts`, `/wishlists` | `POST /items`, `GET /`, `DELETE /items/{id}`, `POST /merge` |
| `/orders` | `POST /` (checkout), `GET /me`, `GET /` (admin), `PATCH /{id}/status` |
| payments (`/api/v1`) | admin lookups by order or reference |
| `/webhooks` | `POST /stripe`, `POST /paystack` |
| `/reviews`, `/admin/analytics` | reviews and dashboard figures |

Full, always-current list: <http://localhost:8000/docs>.

### Payment flow

1. Customer fills the cart and calls `POST /orders/` with `X-Idempotency-Key`.
2. Stock is reserved and the order is `pending`. The API returns a Stripe `client_secret` or a Paystack `access_code`.
3. The frontend completes the payment in the Stripe/Paystack widget.
4. The provider calls our **webhook**. We verify the signature, check the amount, then mark the order `confirmed` (once only).
5. If nobody pays in time, Celery beat cancels the order and returns the stock.

### Order status rules

`pending → confirmed → processing → shipped → delivered`; an order can be cancelled while it is `pending`, `confirmed` or `processing` (a customer may cancel only their own `pending` order). Once `shipped` it can only become `delivered`. `delivered` and `cancelled` are final. Invalid moves return `409`.

## Tests

```bash
# Redis must be running (tests use DB 15)
python -m pytest -q
```

* `tests/conftest.py` – test database (SQLite, rolled back after each test), mocks for Celery, Stripe and Paystack, and helper fixtures (`make_user`, `make_products`, `make_order`, `registered_user`, `login_user`)
* `test_auth.py` – register, verify, login, refresh rotation, logout, password change/reset
* `test_order.py` – checkout, access rules, status transitions, expiry
* `test_payment.py` – Stripe/Paystack initiation, webhooks (confirm, replay, underpaid, bad signature)
* `test_guest.py` – guest cart and wishlist

Tests marked `xfail` describe correct behaviour that currently fails because of a known bug (see below). They turn into `XPASS` once the bug is fixed.

## Known issues found during review

| # | Where | Problem | Fix |
|---|-------|---------|-----|
| B1 | `order_repository.get_with_items` | `Order.payment` is not eager-loaded, so order detail and cancel crash (`MissingGreenlet`) | add `selectinload(Order.payment)` |
| B2 | `user_repository.search_users` | searches names on the wrong table | search `Profile` |
| B3 | `product_service.remove_image` | calls the wrong repository method | use `delete_object` |
| B4 | `product_route.delete_product` | Cloudinary images are not deleted | pass `BackgroundTasks` and call `cloudinary_image.delete_images` |
| B5 | image-delete route | passes a string where a list is expected | pass `[public_id]` |
| B6 | `fulfill_order_status` | reads `order.status` before checking that the order exists | move the `None` check first |

Ready-made patches are in `By-Direct_Backend_Fixes.diff` (B1–B5).

## Troubleshooting

* **Every request returns 500** – Redis is not running (the rate limiter needs it).
* **`MissingGreenlet` error** – a relationship was lazy-loaded in async code; load it with `selectinload`.
* **No emails arrive** – Celery worker is not running, or the SMTP app password is wrong.
* **CORS error in the browser** – add the frontend URL to `ALLOWED_ORIGINS`.
* Remove the stray `dump.rdb` (a Redis dump) from the project folder and add it to `.gitignore`.
