"""Payments: Stripe / Paystack initialisation, webhooks (confirm order), admin lookups."""
import hashlib
import hmac
import json

import pytest
import stripe
from app.core.config import settings
from app.core.enums import OrderStatus, PaymentStatus, UserRole
from app.models import Order, Payment
from conftest import auth_header
from sqlalchemy import select

CHECKOUT = {"shipping_address": {"street": "12 Allen Avenue", "city": "Ikeja", "country": "NG"}, "payment_provider": "stripe"}


async def _checkout(client, user, product, provider="stripe", key="k1"):
    h = auth_header(user)
    await client.post("/api/v1/carts/items", json={"product_id": product.id, "quantity": 1}, headers=h)
    body = {**CHECKOUT, "payment_provider": provider}
    return await client.post("/api/v1/orders/", json=body, headers={**h, "X-Idempotency-Key": key})


# ---------------------------------------------------------------- initialising a payment
async def test_stripe_checkout_creates_pending_payment(client, db_session, make_user, make_products, mock_stripe):
    user = await make_user("stripe@example.com")
    [product] = await make_products(1)
    r = await _checkout(client, user, product)
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"client_secret", "payment_intent_id"}

    order = (await db_session.execute(select(Order).where(Order.user_id == user.id))).scalar_one()
    payment = (await db_session.execute(select(Payment).where(Payment.order_id == order.id))).scalar_one()
    assert payment.status == PaymentStatus.PENDING
    assert payment.provider_reference == r.json()["payment_intent_id"]
    # Stripe takes the smallest unit: kobo
    sent = mock_stripe.call_args.kwargs
    assert sent["amount"] == int(order.total_amount * 100) and sent["currency"] == "ngn"
    assert sent["metadata"]["order_id"] == str(order.id)


async def test_stripe_error_becomes_400(client, make_user, make_products, monkeypatch):
    async def boom(**kw):
        raise stripe.InvalidRequestError("bad request", param=None)

    monkeypatch.setattr(stripe.PaymentIntent, "create_async", boom)
    user = await make_user("stripefail@example.com")
    [product] = await make_products(1)
    assert (await _checkout(client, user, product)).status_code == 400


async def test_paystack_checkout_returns_access_code(client, db_session, make_user, make_products, mock_paystack):
    user = await make_user("paystack@example.com")
    [product] = await make_products(1)
    r = await _checkout(client, user, product, provider="paystack")
    assert r.status_code == 200, r.text
    assert r.json()["access_code"] == "ac_test"
    order = (await db_session.execute(select(Order).where(Order.user_id == user.id))).scalar_one()
    payment = (await db_session.execute(select(Payment).where(Payment.order_id == order.id))).scalar_one()
    assert payment.provider.value == "paystack" and payment.provider_reference.startswith("pay-")
    assert mock_paystack[0]["json"]["amount"] == int(order.total_amount * 100)


# ---------------------------------------------------------------- Stripe webhook
def _stripe_event(monkeypatch, order, user, amount, event_id="evt_1", etype="payment_intent.succeeded"):
    event = stripe.Event.construct_from({
        "id": event_id, "type": etype,
        "data": {"object": {"id": "pi_1", "amount_received": amount, "currency": "ngn",
                            "metadata": {"order_id": str(order.id), "user_id": str(user.id), "email": user.email,
                                         "idempotency_key": f"stripe_payment:{order.id}:{order.order_number}"}}},
    }, "key")
    monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **k: event))


async def _post_stripe(client):
    return await client.post("/api/v1/webhooks/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=x"})


async def test_stripe_webhook_confirms_order_and_payment(client, db_session, make_user, make_products, make_order, monkeypatch, mock_background_jobs):
    user = await make_user("hook@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product)
    _stripe_event(monkeypatch, order, user, amount=12000)          # 120.00 naira in kobo

    r = await _post_stripe(client)
    assert r.status_code == 200
    await db_session.refresh(order)
    payment = (await db_session.execute(select(Payment).where(Payment.order_id == order.id))).scalar_one()
    await db_session.refresh(payment)
    assert order.status == OrderStatus.CONFIRMED
    assert payment.status == PaymentStatus.COMPLETED
    assert len(mock_background_jobs["order"]) == 1                 # confirmation email queued


async def test_stripe_webhook_replay_is_ignored(client, db_session, make_user, make_products, make_order, monkeypatch, mock_background_jobs):
    user = await make_user("replay@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product)
    _stripe_event(monkeypatch, order, user, amount=12000)
    await _post_stripe(client)
    again = await _post_stripe(client)
    assert again.status_code == 200
    assert len(mock_background_jobs["order"]) == 1                 # no second email, no second confirmation


async def test_stripe_webhook_underpayment_does_not_confirm(client, db_session, make_user, make_products, make_order, monkeypatch):
    user = await make_user("under@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product)
    _stripe_event(monkeypatch, order, user, amount=5000)           # paid 50.00 of 120.00
    assert (await _post_stripe(client)).status_code == 200
    await db_session.refresh(order)
    assert order.status == OrderStatus.PENDING


async def test_stripe_webhook_for_cancelled_order_is_not_confirmed(client, db_session, make_user, make_products, make_order, monkeypatch):
    user = await make_user("latepay@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product, status=OrderStatus.CANCELLED)
    _stripe_event(monkeypatch, order, user, amount=12000)
    assert (await _post_stripe(client)).status_code == 200
    await db_session.refresh(order)
    assert order.status == OrderStatus.CANCELLED


async def test_stripe_webhook_rejects_bad_signature(client, monkeypatch):
    def bad(*a, **k):
        raise stripe.SignatureVerificationError("bad", "sig")

    monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(bad))
    assert (await _post_stripe(client)).status_code == 400


async def test_stripe_webhook_needs_signature_header(client):
    assert (await client.post("/api/v1/webhooks/stripe", content=b"{}")).status_code == 400


@pytest.mark.xfail(reason="BUG: fulfill_order_status reads order.status before checking the order exists (AttributeError)", raises=Exception)
async def test_stripe_webhook_for_unknown_order_is_ignored(client, make_user, monkeypatch):
    user = await make_user("ghost@example.com")
    ghost = Order(id=9999, order_number="ORD-GHOST")
    _stripe_event(monkeypatch, ghost, user, amount=12000)
    assert (await _post_stripe(client)).status_code == 200


# ---------------------------------------------------------------- Paystack webhook
def _paystack_body(order, user, amount, event="charge.success"):
    return json.dumps({"event": event, "data": {
        "id": 1, "amount": amount, "currency": "NGN", "reference": "pay-ABC", "gateway_response": "Successful",
        "metadata": {"order_id": order.id, "user_id": user.id, "email": user.email, "idempotency_key": f"paystack_payment:{order.id}"}}}).encode()


def _paystack_sign(body: bytes) -> dict:
    key = settings.PAYSTACK_SECRET_KEY.get_secret_value().encode()
    return {"x-paystack-signature": hmac.new(key, body, hashlib.sha512).hexdigest()}


async def test_paystack_webhook_confirms_order(client, db_session, make_user, make_products, make_order):
    user = await make_user("psk@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product)
    body = _paystack_body(order, user, 12000)
    r = await client.post("/api/v1/webhooks/paystack", content=body, headers=_paystack_sign(body))
    assert r.status_code == 200
    await db_session.refresh(order)
    assert order.status == OrderStatus.CONFIRMED


async def test_paystack_webhook_rejects_wrong_signature(client, db_session, make_user, make_products, make_order):
    user = await make_user("psk2@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product)
    body = _paystack_body(order, user, 12000)
    r = await client.post("/api/v1/webhooks/paystack", content=body, headers={"x-paystack-signature": "0" * 128})
    assert r.status_code == 400
    await db_session.refresh(order)
    assert order.status == OrderStatus.PENDING


async def test_paystack_webhook_underpayment_does_not_confirm(client, db_session, make_user, make_products, make_order):
    user = await make_user("psk3@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product)
    body = _paystack_body(order, user, 100)
    await client.post("/api/v1/webhooks/paystack", content=body, headers=_paystack_sign(body))
    await db_session.refresh(order)
    assert order.status == OrderStatus.PENDING


# ---------------------------------------------------------------- admin payment endpoints
async def test_admin_can_find_payment_by_order(client, make_user, make_products, make_order):
    admin, user = await make_user("padm@example.com", role=UserRole.ADMIN), await make_user("pcust@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product)
    r = await client.get("/api/v1/", params={"order_id": order.id}, headers=auth_header(admin))
    assert r.status_code == 200 and r.json()["order_id"] == order.id


async def test_payment_lookup_needs_a_filter(client, make_user):
    admin = await make_user("padm2@example.com", role=UserRole.ADMIN)
    assert (await client.get("/api/v1/", headers=auth_header(admin))).status_code == 400


async def test_customer_cannot_see_payments(client, make_user):
    user = await make_user("pcust2@example.com")
    assert (await client.get("/api/v1/all", headers=auth_header(user))).status_code == 403


async def test_only_superadmin_can_delete_payment(client, make_user, make_products, make_order):
    admin, sup = await make_user("padm3@example.com", role=UserRole.ADMIN), await make_user("psup@example.com", role=UserRole.SUPERADMIN)
    user = await make_user("pcust3@example.com")
    [product] = await make_products(1)
    await make_order(user, product)
    assert (await client.delete("/api/v1/1", headers=auth_header(admin))).status_code == 403
    assert (await client.delete("/api/v1/1", headers=auth_header(sup))).status_code == 204
