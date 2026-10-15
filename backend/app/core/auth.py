
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl='auth/login',
)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate credentials',
        headers={'WWW-Authenticate': 'Bearer'},
    )

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={'require': ['exp', 'sub']},
        )

        subject = payload.get('sub')

        if not isinstance(subject, str):
            raise credentials_exception

        user_id = UUID(subject)

    except (InvalidTokenError, ValueError):
        raise credentials_exception from None

    user = await session.get(User, user_id)

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Inactive user',
        )

    return user

user_dependency = Annotated[User, Depends(get_current_user)]