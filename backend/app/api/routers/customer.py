from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.core.database import session_Dependency
from app.core.auth import user_dependency
from app.models.user import User
from app.schemas.users import UserRead


router = APIRouter(
    prefix="/api/v1/users",
    tags=["users"],
)


@router.get("/me", response_model=UserRead)
async def me(
    session: session_Dependency,
    user: user_dependency,
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    result = await session.exec(
        select(User).where(User.id == user.id)
    )

    current_user = result.first()

    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        )

    return current_user