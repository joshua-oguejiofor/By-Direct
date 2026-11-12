"""
Who is calling? A logged-in user, or an anonymous guest.

- Logged in  -> Visitor(user=<User>)
- Guest      -> Visitor(guest_id="<uuid hex>")   (id comes from a cookie / X-Guest-Id header)

Only cart and wishlist routes (and the public product routes) use this.
Checkout, orders, reviews and profile keep using get_current_user (login required).

If no token it return None without trowing error. This is only limited to public route(product view, guest cart and guest wishlist)

"""
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, Response
from fastapi.security import OAuth2PasswordBearer

from app.core import exceptions
from app.core.config import settings
from app.depends.current_user import DBSessionDep, get_current_user
from app.models.user import User

# auto_error=False -> no token means "guest" instead of a 401
oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)




async def get_optional_user(
    db: DBSessionDep,
    token: Annotated[str | None, Depends(oauth2_optional)] = None,
) -> User | None:
    
    """None for guests. A token that is present but bad/expired still gives 401."""
    if token is None:
        return None
    return await get_current_user(db=db, token=token)


def read_guest_id(request: Request) -> str | None:
    """Return a valid guest id from the header or cookie, or None.
    The id is parsed as a UUID so nobody can use it to build odd Redis keys."""
    for raw in (
        request.headers.get(settings.GUEST_HEADER), request.cookies.get(settings.GUEST_COOKIE)
        ):
        if raw:
            try:
                return uuid.UUID(raw).hex
            except ValueError:
                continue
    return None

def read_idempotency_key(request: Request) -> str | None:
    """
    Extracts the idempotency key from the request headers.
    Checks common header variations (X-Idempotency-Key or Idempotency-Key).
    """
    raw = request.headers.get("X-Idempotency-Key")
    if not raw or not isinstance(raw, str):
        raise exceptions.BadRequestError("Missing X-Idempotency-Key")
    return raw.strip()


@dataclass
class Visitor:
    user: User | None = None
    guest_id: str | None = None


async def get_visitor(
    request: Request,
    response: Response,
    user: Annotated[User | None, Depends(get_optional_user)],
) -> Visitor:
    if user is not None:
        return Visitor(user=user)

    guest_id = read_guest_id(request) or uuid.uuid4().hex
    # (re)set the cookie so it keeps living while the guest is active
    response.set_cookie(
        settings.GUEST_COOKIE, guest_id,
        max_age=settings.GUEST_TTL_SECONDS, httponly=True, samesite="lax",
        secure=not settings.DEBUG,
    )
    # also hand it to the frontend (for apps on another domain that cannot use the cookie)
    response.headers[settings.GUEST_HEADER] = guest_id
    return Visitor(guest_id=guest_id)


visitor_ = Annotated[Visitor, Depends(get_visitor)]
optional_user_ = Annotated[User | None, Depends(get_optional_user)]
