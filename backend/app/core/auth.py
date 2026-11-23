import logging
import re
from typing import Annotated

from clerk_backend_api import Clerk
from clerk_backend_api.security.types import (
    AuthenticateRequestOptions,
    RequestState,
)
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.database import get_db
from app.enums.enums import Role
from app.models.user import User

clerk_client = Clerk(
    bearer_auth=settings.CLERK_SECRET_KEY,
)

logger = logging.getLogger(__name__)


def _normalize_email(value: str | None) -> str | None:
    """Trim and lowercase an email for comparison, or ``None`` if empty."""
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _primary_email(clerk_user) -> object | None:
    """The Clerk email object marked as the user's primary address."""
    email_addresses = clerk_user.email_addresses or []
    return next(
        (
            address
            for address in email_addresses
            if address.id == clerk_user.primary_email_address_id
        ),
        None,
    )


def _is_verified(email_address) -> bool:
    """Whether a Clerk email address has a verified verification status."""
    verification = getattr(email_address, "verification", None)
    verification_status = getattr(verification, "status", None)
    verification_value = getattr(
        verification_status,
        "value",
        verification_status,
    )
    return verification_value == "verified"


def _verified_primary_email(clerk_user) -> str | None:
    """Normalized verified primary email, or ``None`` when unavailable.

    Returns ``None`` unless Clerk reports a primary email address that is
    verified, so an unverified or missing address can never be treated as an
    authoritative identity.
    """
    primary_email = _primary_email(clerk_user)
    if primary_email is None or not _is_verified(primary_email):
        return None
    return _normalize_email(getattr(primary_email, "email_address", None))


def require_auth(request: Request) -> RequestState:
    state = clerk_client.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=settings.allowed_origins,
            accepts_token=["session_token"],
        ),
    )

    if not state.is_signed_in:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Clerk session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return state


async def _reconcile_owner_for(user: User, *, session, clerk_user=None) -> User:
    """Reconcile the OWNER role for ``user`` against ``OWNER_EMAIL``.

    Imported lazily to avoid a circular import: ``owner_identity`` reuses the
    email-verification helpers defined in this module. Any failure here is
    non-fatal — the request continues with the stored role — because ownership
    reconciliation must never make authentication unavailable.
    """
    try:
        from app.core.config import settings
        from app.services.owner_identity import normalize_email, reconcile_owner

        configured = settings.owner_email
        if configured is None:
            return user

        # Fast path: a user who already holds OWNER can never be *changed* by
        # reconciliation. ``evaluate`` returns ALREADY_OWNER (or NOT_VERIFIED)
        # for the current Owner, both ``changed == False``, so the atomic apply
        # path — which acquires a transaction advisory lock and calls Clerk to
        # verify the email — cannot alter anything for them. Skipping it removes
        # one Neon round-trip and one Clerk API call from *every* authenticated
        # request the Owner makes (the common case for the person browsing the
        # dashboard/tickets). Recognition of a *new* configured owner is
        # unaffected: that person is not yet OWNER, so they take the full path and
        # are promoted exactly as before.
        if user.role == Role.OWNER:
            return user

        # Second fast path: reconciliation can only ever promote the candidate
        # whose stored email matches ``OWNER_EMAIL`` (this is exactly the
        # condition ``owner_identity.find_candidate_by_email`` — used by startup
        # reconciliation and the manual command — relies on). For every *other*
        # authenticated user the outcome is always a no-op, so taking the
        # transaction-scoped advisory lock and making a live Clerk call on each
        # of their requests only serialises all non-owner traffic behind one
        # global lock and adds an external round-trip, with no possible effect on
        # the role. The intended owner's local email is populated from their
        # verified Clerk primary address when the account is provisioned, so
        # their promotion is unaffected.
        if normalize_email(user.email) != configured:
            return user

        decision = await reconcile_owner(
            session,
            clerk=clerk_client,
            candidate=user,
            configured_email=configured,
            clerk_user=clerk_user,
        )
        if decision.changed:
            await session.refresh(user)
        return user
    except Exception:  # noqa: BLE001 - authentication must keep working
        # A sanitized warning only; never the address or a Clerk secret.
        logger.warning(
            "Owner reconciliation skipped for this request; stored role kept"
        )
        return user


async def get_current_user(
    state: Annotated[RequestState, Depends(require_auth)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    clerk_user_id = state.payload.get("sub")

    if not isinstance(clerk_user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Clerk user ID",
        )

    # 1. Find the existing local user.
    result = await session.exec(select(User).where(User.clerk_id == clerk_user_id))
    user = result.first()

    if user is not None:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user",
            )
        # The stored role is authoritative for ordinary roles. The only value
        # that is re-evaluated on the request path is OWNER, and only against the
        # configured OWNER_EMAIL and the identity's *verified Clerk primary*
        # email. This is what makes a configured owner recognised automatically
        # on sign-in without any manual role edit, and what makes an OWNER_EMAIL
        # change take effect on the next authenticated request.
        user = await _reconcile_owner_for(user, session=session)
        return user

    # 2. Fetch the user from Clerk if no local profile exists.
    try:
        clerk_user = await clerk_client.users.get_async(
            user_id=clerk_user_id,
        )
    except Exception:  # noqa: BLE001 - SDK/network failures need one safe 502
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve the Clerk user profile",
        ) from None

    # 3. Require a verified primary email address.
    primary_email = _primary_email(clerk_user)

    if primary_email is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A primary email address is required",
        )

    if not _is_verified(primary_email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email address before using HelpDesk",
        )

    email = _normalize_email(getattr(primary_email, "email_address", None))

    if email is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A primary email address is required",
        )

    # 4. Link an existing HelpDesk account by verified email.
    result = await session.exec(select(User).where(User.email == email))
    existing_user = result.first()

    if existing_user is not None:
        if existing_user.clerk_id not in (None, clerk_user_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is linked to another account",
            )

        existing_user.clerk_id = clerk_user_id
        existing_user.password_hash = None
        # Refresh the cached Clerk profile image on (re)link. The value always
        # comes from Clerk, never from the request.
        existing_user.image_url = getattr(clerk_user, "image_url", None)

        # Ordinary roles are preserved while linking; the only role that is
        # re-evaluated is OWNER, and only against OWNER_EMAIL plus the verified
        # Clerk primary email (checked below, after the link commits).
        try:
            await session.commit()
            await session.refresh(existing_user)
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not link this HelpDesk account",
            ) from None

        user = existing_user

    else:
        # 5. Create a local profile for a new Clerk user. Ordinary users are
        # always provisioned as CUSTOMER; the role is decided here, never from
        # the request. OWNER is only ever granted by the explicit one-time
        # bootstrap command, so public sign-up can never produce an Owner.
        #
        # The Clerk SDK's ``User`` model exposes ``username``/``first_name``/
        # ``last_name`` as *nullable* optional attributes: they exist but may be
        # ``None``, and a test double or an older SDK response may omit them
        # entirely. Read them defensively so provisioning never fails on a
        # missing optional field.
        username_source = (
            getattr(clerk_user, "username", None)
            or email.partition("@")[0]
            or "customer"
        )

        username_base = (
            re.sub(
                r"[^a-zA-Z0-9_.-]",
                "_",
                username_source,
            ).strip("._-")
            or "customer"
        )

        username = f"{username_base[:70]}_{clerk_user_id[-8:]}"

        full_name = (
            " ".join(
                part
                for part in (
                    getattr(clerk_user, "first_name", None),
                    getattr(clerk_user, "last_name", None),
                )
                if part
            ).strip()
            or username
        )

        user = User(
            clerk_id=clerk_user_id,
            full_name=full_name[:120],
            username=username,
            email=email,
            password_hash=None,
            role=Role.CUSTOMER,
            is_active=True,
            # Clerk's image is authoritative; cache it for other-user rendering.
            image_url=getattr(clerk_user, "image_url", None),
        )

        session.add(user)

        try:
            await session.commit()
            await session.refresh(user)
        except IntegrityError:
            await session.rollback()

            # Handle simultaneous requests that created the profile.
            result = await session.exec(
                select(User).where(User.clerk_id == clerk_user_id)
            )
            user = result.first()

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not create the HelpDesk user profile",
                ) from None

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    # 6. Automatic Owner recognition for a freshly provisioned or newly linked
    #    account. This reuses the already-verified ``clerk_user`` so no second
    #    Clerk call is made, and it is a no-op unless OWNER_EMAIL is configured
    #    and matches the verified primary email.
    user = await _reconcile_owner_for(user, session=session, clerk_user=clerk_user)

    return user


def require_roles(*allowed_roles: Role):
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
        return current_user

    return role_checker


user_dependency = Annotated[
    User,
    Depends(get_current_user),
]

# Administrative capabilities (dashboard, ticket management, assignment).
# The Owner is a super-administrator, so it is included here as well.
admin_dependency = Annotated[
    User,
    Depends(require_roles(Role.ADMIN, Role.OWNER)),
]

# Owner only: exclusive user-management authority (roles and account status).
owner_dependency = Annotated[
    User,
    Depends(require_roles(Role.OWNER)),
]

# Agent only. Deliberately excludes ADMIN and OWNER: the agent queue is
# agent-only and administrative privileges never grant agent-specific actions.
agent_dependency = Annotated[
    User,
    Depends(require_roles(Role.AGENT)),
]

# Anyone who works on tickets (agent, admin or owner).
staff_dependency = Annotated[
    User,
    Depends(require_roles(Role.AGENT, Role.ADMIN, Role.OWNER)),
]

# Customer only
customer_dependency = Annotated[
    User,
    Depends(require_roles(Role.CUSTOMER)),
]

# Everyone who is not an agent (customer, admin or owner). Rarely needed, kept
# for symmetry and to show how role groups can be composed.
admin_or_customer_dependency = Annotated[
    User,
    Depends(require_roles(Role.ADMIN, Role.OWNER, Role.CUSTOMER)),
]
