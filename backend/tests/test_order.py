"""Orders: checkout, listing, access rules, status changes, expiry.

Tests marked xfail describe behaviour that is CORRECT but currently crashes because of a known bug
(see the bug list). Once the bug is fixed they turn into XPASS, which is expected.
"""
import pytest
from app.core.enums import OrderStatus, UserRole
from app.models import CartItem, Order, Product
from conftest import auth_header
from sqlalchemy import select

ORDERS = "/api/v1/orders"
CHECKOUT = {"shipping_address": {"street": "12 Allen Avenue", "city": "Ikeja", "country": "NG"}, "payment_provider": "stripe"}


async def _fill_cart(client, headers, product, qty=2):
    r = await client.post("/api/v1/carts/items", json={"product_id": product.id, "quantity": qty}, headers=headers)
    assert r.status_code == 201, r.text


def _idem(key="key-1"):
    return {"X-Idempotency-Key": key}


# ---------------------------------------------------------------- checkout
async def test_checkout_creates_pending_order_and_reserves_stock(client, db_session, make_user, make_products, mock_stripe):
    user = await make_user("buyer@example.com")
    [product] = await make_products(1, stock=10)
    h = auth_header(user)
    await _fill_cart(client, h, product, qty=2)

    r = await client.post(f"{ORDERS}/", json=CHECKOUT, headers={**h, **_idem()})
    assert r.status_code == 200, r.text
    assert r.json()["client_secret"].startswith("cs_test")

    order = (await db_session.execute(select(Order).where(Order.user_id == user.id))).scalar_one()
    assert order.status == OrderStatus.PENDING
    assert order.subtotal == 200                                  # 2 x 100.00
    assert order.total_amount > order.subtotal                    # tax + shipping were added by the server
    stock = (await db_session.execute(select(Product.stock_quantity).where(Product.id == product.id))).scalar_one()
    assert stock == 8                                             # reserved until paid or expired


async def test_checkout_uses_profile_name_and_phone(client, db_session, make_user, make_products, mock_stripe):
    user = await make_user("profile@example.com")
    [product] = await make_products(1)
    h = auth_header(user)
    await _fill_cart(client, h, product)
    r = await client.post(f"{ORDERS}/", json=CHECKOUT, headers={**h, **_idem()})
    assert r.status_code == 200, r.text
    order = (await db_session.execute(select(Order).where(Order.user_id == user.id))).scalar_one()
    assert order.shipping_address["name"] == "john doe"           # first + last name, not just one of them
    assert order.contact_number.startswith("+234")


async def test_checkout_without_profile_needs_name_and_phone(client, make_user, make_products, mock_stripe):
    user = await make_user("noprofile@example.com", profile=False)
    [product] = await make_products(1)
    h = auth_header(user)
    await _fill_cart(client, h, product)
    r = await client.post(f"{ORDERS}/", json=CHECKOUT, headers={**h, **_idem()})
    assert r.status_code == 400


async def test_checkout_requires_login(client):
    assert (await client.post(f"{ORDERS}/", json=CHECKOUT, headers=_idem())).status_code == 401


async def test_checkout_requires_idempotency_key(client, make_user, make_products):
    user = await make_user("idem@example.com")
    [product] = await make_products(1)
    h = auth_header(user)
    await _fill_cart(client, h, product)
    assert (await client.post(f"{ORDERS}/", json=CHECKOUT, headers=h)).status_code == 400


async def test_checkout_empty_cart(client, make_user, mock_stripe):
    user = await make_user("empty@example.com")
    r = await client.post(f"{ORDERS}/", json=CHECKOUT, headers={**auth_header(user), **_idem()})
    assert r.status_code == 400


async def test_checkout_not_enough_stock(client, db_session, make_user, make_products, mock_stripe):
    user = await make_user("stock@example.com")
    [product] = await make_products(1, stock=5)
    h = auth_header(user)
    await _fill_cart(client, h, product, qty=3)
    product.stock_quantity = 1                                    # someone else bought it meanwhile
    await db_session.flush()
    r = await client.post(f"{ORDERS}/", json=CHECKOUT, headers={**h, **_idem()})
    assert r.status_code == 400


async def test_checkout_same_key_twice_makes_one_order(client, db_session, make_user, make_products, mock_stripe):
    user = await make_user("twice@example.com")
    [product] = await make_products(1, stock=10)
    h = {**auth_header(user), **_idem("same-key")}
    await _fill_cart(client, auth_header(user), product, qty=2)
    first = await client.post(f"{ORDERS}/", json=CHECKOUT, headers=h)
    second = await client.post(f"{ORDERS}/", json=CHECKOUT, headers=h)
    assert first.status_code == second.status_code == 200
    orders = (await db_session.execute(select(Order).where(Order.user_id == user.id))).scalars().all()
    assert len(orders) == 1
    stock = (await db_session.execute(select(Product.stock_quantity).where(Product.id == product.id))).scalar_one()
    assert stock == 8                                             # stock reserved only once


async def test_checkout_validates_address(client, make_user, make_products):
    user = await make_user("addr@example.com")
    [product] = await make_products(1)
    h = auth_header(user)
    await _fill_cart(client, h, product)
    bad = {"shipping_address": {"street": "x", "city": "Ikeja", "country": "NGA"}, "payment_provider": "stripe"}
    assert (await client.post(f"{ORDERS}/", json=bad, headers={**h, **_idem()})).status_code == 422


# ---------------------------------------------------------------- reading orders
async def test_my_orders_only_shows_my_orders(client, make_user, make_products, make_order):
    me, other = await make_user("me@example.com"), await make_user("other@example.com")
    [product] = await make_products(1)
    await make_order(me, product)
    await make_order(other, product)
    r = await client.get(f"{ORDERS}/me", headers=auth_header(me))
    assert r.status_code == 200
    assert r.json()["count"] == 1


async def test_only_admin_can_list_all_orders(client, make_user, make_products, make_order):
    cust, admin = await make_user("c@example.com"), await make_user("a@example.com", role=UserRole.ADMIN)
    [product] = await make_products(1)
    await make_order(cust, product)
    assert (await client.get(f"{ORDERS}/", headers=auth_header(cust))).status_code == 403
    r = await client.get(f"{ORDERS}/", headers=auth_header(admin))
    assert r.status_code == 200 and r.json()["count"] == 1


@pytest.mark.xfail(reason="BUG: OrderRepository.get_with_items does not load Order.payment (MissingGreenlet)", raises=Exception)
async def test_order_detail_includes_items_and_payment(client, make_user, make_products, make_order):
    user = await make_user("detail@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product)
    r = await client.get(f"{ORDERS}/{order.id}/payment", headers=auth_header(user))
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1 and body["payment"]["status"] == "pending"


@pytest.mark.xfail(reason="BUG: OrderRepository.get_with_items does not load Order.payment (MissingGreenlet)", raises=Exception)
async def test_cannot_read_someone_elses_order(client, make_user, make_products, make_order):
    owner, intruder = await make_user("owner@example.com"), await make_user("intruder@example.com")
    [product] = await make_products(1)
    order = await make_order(owner, product)
    r = await client.get(f"{ORDERS}/{order.id}/payment", headers=auth_header(intruder))
    assert r.status_code in (403, 404)


# ---------------------------------------------------------------- status changes
def _status(order_id, status, reason=None):
    return {"url": f"{ORDERS}/{order_id}/status", "json": {"new_status": status, "reason": reason}}


async def test_customer_cannot_advance_own_order(client, make_user, make_products, make_order):
    user = await make_user("sneaky@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product, status=OrderStatus.CONFIRMED)
    for target in ("processing", "shipped", "delivered"):
        r = await client.patch(**_status(order.id, target), headers=auth_header(user))
        assert r.status_code == 403


async def test_admin_moves_order_forward(client, db_session, make_user, make_products, make_order):
    admin, user = await make_user("adm@example.com", role=UserRole.ADMIN), await make_user("cust@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product, status=OrderStatus.CONFIRMED)
    for target in ("processing", "shipped", "delivered"):
        r = await client.patch(**_status(order.id, target), headers=auth_header(admin))
        assert r.status_code == 200, r.text
    await db_session.refresh(order)
    assert order.status == OrderStatus.DELIVERED


async def test_invalid_transition_is_rejected(client, make_user, make_products, make_order):
    admin, user = await make_user("adm2@example.com", role=UserRole.ADMIN), await make_user("cust2@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product, status=OrderStatus.PENDING)
    r = await client.patch(**_status(order.id, "delivered"), headers=auth_header(admin))   # pending -> delivered is not allowed
    assert r.status_code == 409


async def test_delivered_order_is_final(client, make_user, make_products, make_order):
    admin, user = await make_user("adm3@example.com", role=UserRole.ADMIN), await make_user("cust3@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product, status=OrderStatus.DELIVERED)
    assert (await client.patch(**_status(order.id, "processing"), headers=auth_header(admin))).status_code == 409


@pytest.mark.xfail(reason="BUG: cancel reads order.payment which is not loaded (MissingGreenlet)", raises=Exception)
async def test_customer_can_cancel_own_pending_order_and_stock_returns(client, db_session, make_user, make_products, make_order):
    user = await make_user("cancel@example.com")
    [product] = await make_products(1, stock=10)
    order = await make_order(user, product, status=OrderStatus.PENDING)
    r = await client.patch(**_status(order.id, "cancelled", "changed my mind"), headers=auth_header(user))
    assert r.status_code == 200
    await db_session.refresh(order)
    assert order.status == OrderStatus.CANCELLED
    await db_session.refresh(product)
    assert product.stock_quantity == 11


async def test_customer_cannot_cancel_after_confirmation(client, make_user, make_products, make_order):
    user = await make_user("late@example.com")
    [product] = await make_products(1)
    order = await make_order(user, product, status=OrderStatus.CONFIRMED)
    assert (await client.patch(**_status(order.id, "cancelled"), headers=auth_header(user))).status_code == 403


async def test_other_customer_cannot_touch_my_order(client, make_user, make_products, make_order):
    owner, intruder = await make_user("o2@example.com"), await make_user("i2@example.com")
    [product] = await make_products(1)
    order = await make_order(owner, product, status=OrderStatus.PENDING)
    assert (await client.patch(**_status(order.id, "cancelled"), headers=auth_header(intruder))).status_code == 403


# ---------------------------------------------------------------- expiry
async def test_expired_pending_orders_are_cancelled_and_restocked(db_session, make_user, make_products, make_order):
    from app.depends import di_injection

    user = await make_user("expire@example.com")
    [product] = await make_products(1, stock=10)
    expired = await make_order(user, product, status=OrderStatus.PENDING, expired=True)
    fresh = await make_order(user, product, status=OrderStatus.PENDING, expired=False)

    service = di_injection.get_order_service(db_session)
    await service._release_expired_orders()

    await db_session.refresh(expired)
    await db_session.refresh(fresh)
    await db_session.refresh(product)
    assert expired.status == OrderStatus.CANCELLED
    assert fresh.status == OrderStatus.PENDING                    # not expired: untouched
    assert product.stock_quantity == 11                           # only the expired order was restocked
