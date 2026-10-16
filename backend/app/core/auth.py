from typing import Annotated

from clerk_backend_api import Clerk
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User


clerk = Clerk(
    bearer_auth=settings.CLERK_SECRET_KEY,
)


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    authorization = request.headers.get("Authorization", "")

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        claims = clerk.verify_token(token)
        clerk_user_id = claims.get("sub")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Clerk session",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    if not isinstance(clerk_user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Clerk user ID",
        )

    result = await session.exec(
        select(User).where(User.clerk_id == clerk_user_id)
    )
    user = result.first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HelpDesk profile not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user


user_dependency = Annotated[User, Depends(get_current_user)]