import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.auth import (
    admin_dependency,
    clerk_client,
    owner_dependency,
    user_dependency,
)
from app.core.database import session_Dependency
from app.core.permissions import is_admin_role, is_owner_role
from app.enums.enums import AssignableRole, Role
from app.models.user import User
from app.schemas.users import (
    UserAdminUpdate,
    UserRead,
    UserRoleUpdate,
    UserStatusUpdate,
    UserUpdate,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


async def _ensure_unique_identity(
    session,
    *,
    username: str | None,
    email: str | None,
    exclude_user_id: uuid.UUID,
) -> None:
    """Reject a username/email that already belongs to another account."""
    if username is None and email is None:
        return

    conditions = []
    if username is not None:
        conditions.append(User.username == username)
    if email is not None:
        conditions.append(User.email == email.lower())

    result = await session.exec(
        select(User).where(or_(*conditions), User.id != exclude_user_id)
    )
    conflict = result.first()
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already taken",
        )


@router.get("/me", response_model=UserRead)
async def get_my_profile(user: user_dependency) -> User:
    """Return the authenticated user's own profile."""
    return user


@router.patch("/me", response_model=UserRead)
async def update_my_profile(
    payload: UserUpdate,
    session: session_Dependency,
    user: user_dependency,
) -> User:
    """Update the fields a user is allowed to change on their own profile.

    ``UserUpdate`` forbids unknown fields, so a request cannot smuggle in
    ``role`` or ``is_active``: changing your own role is impossible here.
    """
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No fields to update",
        )

    email = data.get("email")
    if email is not None:
        data["email"] = str(email).lower()

    await _ensure_unique_identity(
        session,
        username=data.get("username"),
        email=data.get("email"),
        exclude_user_id=user.id,
    )

    for field, value in data.items():
        setattr(user, field, value)

    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already taken",
        ) from None

    await session.refresh(user)
    return user


@router.post("/me/avatar", response_model=UserRead)
async def sync_my_avatar(
    session: session_Dependency,
    user: user_dependency,
) -> User:
    """Refresh the cached profile image from Clerk for the caller.

    Clerk is the source of truth for profile photos. The client uploads the new
    image through Clerk (``user.setProfileImage``), then calls this endpoint so
    the URL used to render *this* user for other participants (comments,
    conversations, staff tables) is refreshed from **verified Clerk data**. The
    request body is ignored: an arbitrary URL can never be stored here, and a
    user can only ever refresh their own photo.
    """
    if not user.clerk_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account is not linked to a Clerk identity",
        )
    try:
        clerk_user = await clerk_client.users.get_async(user_id=user.clerk_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve the Clerk user profile",
        ) from None

    user.image_url = getattr(clerk_user, "image_url", None)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# User management
#
# Reading the directory (list + detail) is available to ADMIN and OWNER because
# administrators legitimately resolve display names across the help desk. Every
# *mutation* (role, account status, or another user's profile) is OWNER-only:
# the Owner has exclusive user-management authority and the backend never
# trusts a role supplied by the client.
# ---------------------------------------------------------------------------


@router.get("", response_model=list[UserRead])
async def list_users(
    session: session_Dependency,
    _admin: admin_dependency,
    role: Annotated[Role | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    """List users with optional filters and pagination (admin/owner)."""
    statement = select(User)
    if role is not None:
        statement = statement.where(User.role == role)
    if is_active is not None:
        statement = statement.where(User.is_active == is_active)
    if q:
        like = f"%{q.lower()}%"
        statement = statement.where(
            or_(
                User.username.ilike(like),
                User.email.ilike(like),
                User.full_name.ilike(like),
            )
        )

    statement = statement.order_by(User.created_at.desc()).limit(limit).offset(offset)
    result = await session.exec(statement)
    return list(result.all())


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    session: session_Dependency,
    _admin: admin_dependency,
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user_by_owner(
    user_id: uuid.UUID,
    payload: UserAdminUpdate,
    session: session_Dependency,
    owner: owner_dependency,
) -> User:
    """Update another user's profile, role and account status (owner only)."""
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No fields to update",
        )

    if "role" in data:
        data["role"] = _as_role(data["role"])

    await _guard_managed_user_change(session, owner, target, data)

    email = data.get("email")
    if email is not None:
        data["email"] = str(email).lower()

    await _ensure_unique_identity(
        session,
        username=data.get("username"),
        email=data.get("email"),
        exclude_user_id=target.id,
    )

    for field, value in data.items():
        setattr(target, field, value)

    session.add(target)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already taken",
        ) from None

    await session.refresh(target)
    return target


@router.patch("/{user_id}/role", response_model=UserRead)
async def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    session: session_Dependency,
    owner: owner_dependency,
) -> User:
    """Change an eligible user's application role (owner only).

    The request schema only accepts CUSTOMER/AGENT/ADMIN, so this endpoint can
    never create an Owner.
    """
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    new_role = _as_role(payload.role)
    await _guard_managed_user_change(session, owner, target, {"role": new_role})

    target.role = new_role
    session.add(target)
    await session.commit()
    await session.refresh(target)
    return target


@router.patch("/{user_id}/status", response_model=UserRead)
async def update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    session: session_Dependency,
    owner: owner_dependency,
) -> User:
    """Activate or deactivate an eligible non-Owner account (owner only)."""
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await _guard_managed_user_change(
        session, owner, target, {"is_active": payload.is_active}
    )

    target.is_active = payload.is_active
    session.add(target)
    await session.commit()
    await session.refresh(target)
    return target


# ---------------------------------------------------------------------------
# Guard helpers
# ---------------------------------------------------------------------------


def _as_role(value: AssignableRole | Role) -> Role:
    """Coerce an assignable role (or Role) to the domain ``Role`` enum.

    ``AssignableRole`` intentionally excludes OWNER; converting through it keeps
    an Owner value impossible even if a schema were loosened later.
    """
    if isinstance(value, Role):
        return value
    return Role(value.value)


async def _count_admin_like(session, *, exclude_user_id: uuid.UUID) -> int:
    """Number of active administrative accounts (ADMIN or OWNER) other than
    ``exclude_user_id``."""
    result = await session.exec(
        select(func.count())
        .select_from(User)
        .where(
            User.role.in_((Role.ADMIN, Role.OWNER)),
            User.is_active.is_(True),
            User.id != exclude_user_id,
        )
    )
    return result.one()


async def _guard_managed_user_change(
    session,
    actor: User,
    target: User,
    data: dict,
) -> None:
    """Enforce the Owner/user-management invariants.

    Rules:

    * The Owner account is immutable through this interface: its role can never
      be changed and it can never be deactivated. Because no request can assign
      OWNER either, the application can never be left without an Owner.
    * No account may change its own role or deactivate itself.
    * At least one active administrative account (ADMIN or OWNER) must remain,
      which is always satisfied while the permanent Owner exists.
    """
    new_role = data.get("role")
    changing_role = new_role is not None and new_role != target.role
    deactivating = data.get("is_active") is False

    # 1. The permanent Owner is protected.
    if is_owner_role(target.role):
        if changing_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The Owner's role cannot be changed",
            )
        if deactivating:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The Owner account cannot be deactivated",
            )
        return

    # 2. Self-protection.
    if actor.id == target.id:
        if changing_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot change your own role",
            )
        if deactivating:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account",
            )

    # 3. Keep an administrative anchor.
    if is_admin_role(target.role) and (changing_role or deactivating):
        remaining = await _count_admin_like(session, exclude_user_id=target.id)
        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one active administrator must remain",
            )
