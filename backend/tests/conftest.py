"""
Note: The default scope is Function, not specifing scope or setting it as session, pytest falls to its default function
"""



from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest  # noqa: F401, RUF100
import pytest_asyncio
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.database import get_db
from app.core.redis_server import get_redis, redis_manager
from app.main import app
from app.models.base import Base
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


# -----------------------------------------------------------------------------
# Session-Scoped Async Fixtures
# -----------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Creates the async engine once per test session."""
    engine = create_async_engine(
        settings.TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def setup_database(test_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Prepares schema at the start of the session and tears it down at the end."""
    async with test_engine.begin() as engine:
        await engine.run_sync(Base.metadata.drop_all)
        await engine.run_sync(Base.metadata.create_all)
    
    yield

    async with test_engine.begin() as engine:
        await engine.run_sync(Base.metadata.drop_all)


# -----------------------------------------------------------------------------
# Function-Scoped Async Fixtures
# ----------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine: AsyncEngine, setup_database: None) -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated database session rolled back after every test function."""
    async with test_engine.connect() as conn:
        transaction = await conn.begin()

        session_factory = async_sessionmaker(
            bind=conn,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )

        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()
                if transaction.is_active:
                    await transaction.rollback()



# ============================================================
# REDIS
# ============================================================
@pytest_asyncio.fixture(scope="function", autouse=True)
async def test_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """
    Initializes a test Redis client attached to DB 15.
    Overrides `redis_manager.client` for all application service functions during tests.
    """
    # 1. Connect directly to the test Redis database (DB 15)
    test_client = aioredis.from_url(
        settings.TEST_REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )

    # 2. Flush any leftover keys from previous test runs
    await test_client.flushdb()

    # 3. Preserve any pre-existing client/pool state
    old_client = redis_manager.client

    # 4. Point your application singleton to the test Redis client
    redis_manager.client = test_client

    yield test_client

    # 5. Cleanup: Flush test DB and close test client after test ends
    await test_client.flushdb()
    await test_client.aclose()

    # 6. Restore original client state
    redis_manager.client = old_client


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession, test_redis: aioredis.Redis) -> AsyncGenerator[AsyncClient, None]:
    """Provides an HTTPX AsyncClient with overridden database dependencies."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session
        
    async def override_get_redis():
            yield test_redis
    

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.clear()
        
  


# =============================================================================
# MOCKS (nothing in the tests talks to the internet, Celery, Stripe or Paystack)
# =============================================================================
@pytest.fixture(autouse=True)
def mock_background_jobs(monkeypatch):
    """Emails go through Celery. Replace the dispatch functions so no broker is needed,
    and switch the rate limiter off so 5/minute limits do not break the tests."""
    from app.domains.auth import auth_service
    from app.domains.order import order_service
    from app.middleware import rate_limit

    sent = {"verify": [], "login": [], "otp": [], "order": []}
    monkeypatch.setattr(auth_service, "dispatch_email_verify_token", lambda **kw: sent["verify"].append(kw))
    monkeypatch.setattr(auth_service, "dispatch_login_notification", lambda **kw: sent["login"].append(kw))
    monkeypatch.setattr(auth_service, "dispatch_otp_email", lambda **kw: sent["otp"].append(kw))
    monkeypatch.setattr(order_service, "dispatch_order_comfirmation", lambda **kw: sent["order"].append(kw))
    monkeypatch.setattr(rate_limit.limiter, "enabled", False)
    return sent


@pytest.fixture
def mock_stripe(monkeypatch):
    """Fake stripe.PaymentIntent.create_async. Returns the AsyncMock so a test can inspect the call."""
    import stripe

    counter = {"n": 0}

    async def fake_create(**kwargs):
        counter["n"] += 1
        return MagicMock(id=f"pi_test_{counter['n']}", client_secret=f"cs_test_{counter['n']}")

    mock = AsyncMock(side_effect=fake_create)
    monkeypatch.setattr(stripe.PaymentIntent, "create_async", mock)
    return mock


@pytest.fixture
def mock_paystack(monkeypatch):
    """Fake the HTTP call to https://api.paystack.co/transaction/initialize."""
    import httpx

    calls = []

    real_post = httpx.AsyncClient.post

    async def fake_post(self, url, **kwargs):
        if "paystack.co" not in str(url):          # let the test client's own requests through
            return await real_post(self, url, **kwargs)
        calls.append({"url": url, **kwargs})
        ref = (kwargs.get("json") or {}).get("reference", "pay-TESTREF")
        return httpx.Response(
            200,
            json={"status": True, "data": {"access_code": "ac_test", "reference": ref, "authorization_url": "https://paystack.test/pay"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return calls


# =============================================================================
# DATA HELPERS
# =============================================================================
PASSWORD = "Passw0rd@123"   # meets the password rules: upper, lower, digit, one of + _ @ , -
test_user = {"email": "testuseremail@example.com", "password": PASSWORD}

BASE_URL = "/api/v1/auth"


def auth_header(user) -> dict:
    """Bearer header for a user created straight in the database (skips the login endpoint)."""
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'role': user.role.value if hasattr(user.role, 'value') else user.role})}"}


@pytest_asyncio.fixture
async def make_user(db_session: AsyncSession):
    """make_user("a@x.com", role=UserRole.ADMIN) -> a verified user with a profile."""
    from app.core.enums import UserRole
    from app.core.security import hash_user_password
    from app.models import Profile, User

    async def _make(email: str, role=UserRole.CUSTOMER, profile: bool = True, password: str = PASSWORD):
        user = User(email=email, hashed_password=hash_user_password(password), is_verified=True, role=role)
        db_session.add(user)
        await db_session.flush()
        if profile:
            db_session.add(Profile(user_id=user.id, first_name="john", last_name="doe", phone_number=f"+23480{user.id:08d}", country="ng"))
            await db_session.flush()
        return user

    return _make


@pytest_asyncio.fixture
async def make_products(db_session: AsyncSession):
    """make_products(2, stock=10, price="100.00") -> list of Product rows in a fresh category."""
    from decimal import Decimal
    from itertools import count

    from app.models import Category, Product

    n = count(1)

    async def _make(qty: int = 1, stock: int = 10, price: str = "100.00"):
        k = next(n)
        cat = Category(name=f"cat{k}", slug=f"cat{k}")
        db_session.add(cat)
        await db_session.flush()
        items = []
        for i in range(qty):
            p = Product(name=f"prod{k}{i}", slug=f"prod{k}{i}", price=Decimal(price), stock_quantity=stock, category_id=cat.id, brand="acme")
            db_session.add(p)
            items.append(p)
        await db_session.flush()
        return items

    return _make


@pytest_asyncio.fixture
async def make_order(db_session: AsyncSession):
    """make_order(user, product, status=OrderStatus.PENDING) -> Order (+ Payment) saved in the database."""
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal
    from itertools import count

    from app.core.enums import OrderStatus, PaymentProvider
    from app.models import Order, OrderItem, Payment

    n = count(1)

    async def _make(user, product, status=OrderStatus.PENDING, expired: bool = False, with_payment: bool = True):
        k = next(n)
        order = Order(
            user_id=user.id, order_number=f"ORD-TEST{k:04d}", status=status,
            subtotal=Decimal("100.00"), tax_amount=Decimal("10.00"), shipping_amount=Decimal("10.00"), total_amount=Decimal("120.00"),
            shipping_address={"name": "john doe", "street": "12 allen", "city": "ikeja", "state": None, "postal_code": None,
                              "country": "ng", "notes": None, "payment_provider": "stripe", "contact_number": "+2348011111111"},
            contact_number="+2348011111111",
            expiration_cutoff=datetime.now(UTC) + timedelta(hours=-3 if expired else 2),
        )
        order.items = [OrderItem(product_id=product.id, quantity=1, unit_price=Decimal("100.00"), total_price=Decimal("100.00"), product_name=product.name)]
        db_session.add(order)
        await db_session.flush()
        if with_payment:
            db_session.add(Payment(order_id=order.id, amount=Decimal("120.00"), provider=PaymentProvider.STRIPE, provider_reference=f"pi_{k}"))
            await db_session.flush()
        return order

    return _make


@pytest_asyncio.fixture(scope="function")
async def registered_user(client: AsyncClient, db_session: AsyncSession):
    """Registers a user through the API, then verifies the email with a real token."""
    from app.core import security
    from app.models import User
    from sqlalchemy import select

    reg = await client.post(f"{BASE_URL}/register", json=test_user)
    assert reg.status_code == 201, f"failed to create user: {reg.text}"
    assert reg.json()["msg"] == "Check your email to continue verification process."

    user = (await db_session.execute(select(User).where(User.email == test_user["email"]))).scalar_one()
    token = security.create_email_verification_token({"sub": str(user.id), "jti": "test-verify-jti"})
    verify = await client.get(f"{BASE_URL}/verify-email?token={token}")
    assert verify.status_code == 302

    return {"email": test_user["email"], "password": test_user["password"]}


@pytest_asyncio.fixture(scope="function")
async def login_user(client: AsyncClient, registered_user: dict):

    login_response = await client.post(f"{BASE_URL}/login", data={
        "username": registered_user["email"],
        "password": registered_user["password"],
    })

    assert login_response.status_code == 200, f"Login failed: {login_response.text}"

    access_token = login_response.json()["access_token"]

    assert isinstance(access_token, str)

    client.headers = {**client.headers, "Authorization": f"Bearer {access_token}"}

    yield client


