"""Guest cart + wishlist tests. Uses the same conftest fixtures as the other tests."""
import uuid
from decimal import Decimal

import pytest_asyncio
from app.core.database import get_db
from app.core.enums import UserRole
from app.core.redis_server import redis_manager
from app.core.security import create_access_token
from app.main import app
from app.models import Category, Product, User
from httpx import ASGITransport, AsyncClient

BASE = "/api/v1"


@pytest_asyncio.fixture
async def client(db_session):
    async def _db():
        yield db_session
    app.dependency_overrides[get_db] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def products(db_session):
    cat = Category(name="c", slug="c")
    db_session.add(cat)
    await db_session.flush()
    p1 = Product(name="a", slug="a", price=Decimal("100.00"), discount_price=Decimal("80.00"),
                 stock_quantity=5, category_id=cat.id, brand="b")
    p2 = Product(name="b", slug="b", price=Decimal("50.00"), stock_quantity=3, category_id=cat.id, brand="b")
    p3 = Product(name="off", slug="off", price=Decimal("10.00"), stock_quantity=3,
                 category_id=cat.id, brand="b", is_active=False)
    db_session.add_all([p1, p2, p3])
    await db_session.flush()
    return p1, p2, p3


@pytest_asyncio.fixture
async def auth(db_session):
    u = User(email="u@x.com", hashed_password="x", is_verified=True, role=UserRole.CUSTOMER)
    db_session.add(u)
    await db_session.flush()
    return {"Authorization": f"Bearer {create_access_token({'sub': str(u.id)})}"}


async def test_guest_cart_flow(client, products):
    p1, p2, p3 = products
    r = await client.post(f"{BASE}/carts/items", json={"product_id": p1.id, "quantity": 2})
    assert r.status_code == 201, r.text
    gid = r.headers["x-guest-id"]
    assert "guest_id" in r.cookies
    body = r.json()
    assert body["msg"] 

    # cookie is kept by the client; add more
    r = await client.post(f"{BASE}/carts/items", json={"product_id": p1.id, "quantity": 3})
    assert r.status_code == 201
    assert (await client.get(f"{BASE}/carts/")).json()["items"][0]["quantity"] == 5
    r = await client.post(f"{BASE}/carts/items", json={"product_id": p1.id, "quantity": 1})
    assert r.status_code == 400  # exceeds stock (5)
    r = await client.post(f"{BASE}/carts/items", json={"product_id": p3.id, "quantity": 1})
    assert r.status_code == 404  # inactive product
    r = await client.get(f"{BASE}/carts/")
    assert r.json()["items"][0]["quantity"] == 5
    assert await redis_manager.client.ttl(f"guest_cart:{gid}") > 0

    r = await client.delete(f"{BASE}/carts/items/{p1.id}")
    assert r.status_code == 204
    r = await client.delete(f"{BASE}/carts/items/{p1.id}")
    assert r.status_code == 404
    await client.post(f"{BASE}/carts/items", json={"product_id": p2.id, "quantity": 1})
    r = await client.delete(f"{BASE}/carts/")
    assert r.status_code == 204
    assert (await client.get(f"{BASE}/carts/")).json()["items"] == []


async def test_header_identity_and_bad_id(client, products):
    p1, *_ = products
    gid = uuid.uuid4().hex
    r = await client.post(f"{BASE}/carts/items", json={"product_id": p1.id, "quantity": 1},
                          headers={"X-Guest-Id": gid})
    assert r.headers["x-guest-id"] == gid
    assert await redis_manager.client.hlen(f"guest_cart:{gid}") == 1
    client.cookies.clear()
    r = await client.get(f"{BASE}/carts/", headers={"X-Guest-Id": "../../evil"})
    assert r.status_code == 200 and r.headers["x-guest-id"] != "../../evil"


async def test_guest_wishlist_flow(client, products):
    p1, _p2, p3 = products
    assert (await client.post(f"{BASE}/wishlists/items/{p1.id}")).status_code == 201
    assert (await client.post(f"{BASE}/wishlists/items/{p1.id}")).status_code == 409  # already there
    assert (await client.post(f"{BASE}/wishlists/items/{p3.id}")).status_code == 404
    assert (await client.get(f"{BASE}/wishlists/")).json()["items"] == [{"product_id": p1.id}]
    assert (await client.delete(f"{BASE}/wishlists/items/{p1.id}")).status_code == 204
    assert (await client.delete(f"{BASE}/wishlists/items/{p1.id}")).status_code == 404


async def test_merge_after_login(client, products, auth):
    p1, p2, _ = products
    await client.post(f"{BASE}/carts/items", json={"product_id": p1.id, "quantity": 2})
    await client.post(f"{BASE}/wishlists/items/{p2.id}")
    gid = client.cookies.get("guest_id")

    # user already has p1 x4 in cart
    r = await client.post(f"{BASE}/carts/items", json={"product_id": p1.id, "quantity": 4}, headers=auth)
    assert r.status_code == 201

    r = await client.post(f"{BASE}/carts/merge", headers=auth)
    assert r.status_code == 200
    # 4 + 2 = 6 > stock 5 -> that line is skipped, nothing crashes
    assert r.json() == {"merged": 0, "skipped": 1}
    assert await redis_manager.client.exists(f"guest_cart:{gid}") == 0

    r = await client.post(f"{BASE}/wishlists/merge", headers=auth)
    assert r.json() == {"merged": 1, "skipped": 0}
    r = await client.get(f"{BASE}/wishlists/", headers=auth)
    assert r.status_code == 200

    # no guest id -> nothing to merge
    client.cookies.clear()
    assert (await client.post(f"{BASE}/carts/merge", headers=auth)).json() == {"merged": 0, "skipped": 0}


async def test_logged_in_unchanged_and_merge_needs_login(client, products, auth):
    p1, *_ = products
    r = await client.post(f"{BASE}/carts/items", json={"product_id": p1.id, "quantity": 1}, headers=auth)
    assert r.status_code == 201 and "guest_id" not in r.cookies
    assert (await client.post(f"{BASE}/carts/merge")).status_code == 401
    r = await client.get(f"{BASE}/carts/", headers={"Authorization": "Bearer junk"})
    assert r.status_code == 401


async def test_guest_can_browse_products(client, products):
    r = await client.get(f"{BASE}/products/")
    assert r.status_code == 200, r.text
