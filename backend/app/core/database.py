from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker
from typing import  Annotated
from sqlmodel import SQLModel
from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.engine import Connection

from app.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    connect_args={"check_same_thread": False},
)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session

session_Dependency =  Annotated[AsyncSession, Depends(get_db)]

def create_tables(connection: Connection) -> None:
    SQLModel.metadata.create_all(bind=connection)

async def create_session_and_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(create_tables)