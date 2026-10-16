import re
from typing import Annotated

from clerk_backend_api import Clerk
from clerk_backend_api.security.types import (
    AuthenticateRequestOptions,
    RequestState,
)
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.enums.enums import Role
from app.models.user import User


clerk_client = Clerk(
    bearer_auth=settings.CLERK_SECRET_KEY,
)


def require_auth(request: Request) -> RequestState:
    state = clerk_client.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=[settings.FRONTEND_URL],
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
    result = await session.execute(
        select(User).where(User.clerk_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()

    if user is not None:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user",
            )
        return user

    # 2. Fetch the user from Clerk if no local profile exists.
    try:
        clerk_user = await clerk_client.users.get_async(
            user_id=clerk_user_id,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve the Clerk user profile",
        ) from None

    # 3. Require a verified primary email address.
    email_addresses = clerk_user.email_addresses or []

    primary_email = next(
        (
            address
            for address in email_addresses
            if address.id == clerk_user.primary_email_address_id
        ),
        None,
    )

    if primary_email is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A primary email address is required",
        )

    verification = getattr(primary_email, "verification", None)
    verification_status = getattr(verification, "status", None)
    verification_value = getattr(
        verification_status,
        "value",
        verification_status,
    )

    if verification_value != "verified":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email address before using HelpDesk",
        )

    email = primary_email.email_address.lower()

    # 4. Link an existing HelpDesk account by verified email.
    result = await session.execute(
        select(User).where(User.email == email)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user is not None:
        if existing_user.clerk_id not in (None, clerk_user_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is linked to another account",
            )

        existing_user.clerk_id = clerk_user_id
        existing_user.password_hash = None

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
        # 5. Create a local CUSTOMER profile for a new Clerk user.
        username_source = (
            clerk_user.username
            or email.partition("@")[0]
            or "customer"
        )

        username_base = re.sub(
            r"[^a-zA-Z0-9_.-]",
            "_",
            username_source,
        ).strip("._-") or "customer"

        username = f"{username_base[:70]}_{clerk_user_id[-8:]}"

        full_name = " ".join(
            part
            for part in (
                clerk_user.first_name,
                clerk_user.last_name,
            )
            if part
        ).strip() or username

        user = User(
            clerk_id=clerk_user_id,
            full_name=full_name[:120],
            username=username,
            email=email,
            password_hash=None,
            role=Role.CUSTOMER,
            is_active=True,
        )

        session.add(user)

        try:
            await session.commit()
            await session.refresh(user)
        except IntegrityError:
            await session.rollback()

            # Handle simultaneous requests that created the profile.
            result = await session.execute(
                select(User).where(User.clerk_id == clerk_user_id)
            )
            user = result.scalar_one_or_none()

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

    return user


def require_roles(*allowed_roles: Role):
    async def role_checker(
            current_user: Annotated[
                User,
                Depends(get_current_user)
            ],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Uou do not have permission to access this resource',
            )
        return current_user
    return role_checker

user_dependency = Annotated[
    User,
    Depends(get_current_user),
]

# Admin only
admin_dependency = Annotated[
    User,
    Depends(require_roles(Role.ADMIN)),
]

# Agent only
agency_dependency = Annotated[
    User,
    Depends(require_roles(Role.AGENT)),
]

# Customer only
customer_dependency = Annotated[
    User,
    Depends(require_roles(Role.CUSTOMER)),
]
