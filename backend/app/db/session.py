"""
Database Session Management
KeepGaining Trading Platform

Provides async database connection with:
- Connection pooling
- Context manager support
- Dependency injection for FastAPI
- Health check capabilities
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.core.config import settings


# Create async engine with connection pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.is_development,  # Log SQL in development
    future=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,  # Recycle connections after 30 minutes
    pool_pre_ping=True,  # Verify connections before use
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.
    
    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions.
    
    Usage:
        async with get_db_context() as db:
            result = await db.execute(query)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.
    
    Note: In production, use Alembic migrations instead.
    """
    from app.db.base import Base
    # Import models module to register all models with Base
    from app.db import models  # noqa: F401
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()


class DatabaseService:
    """
    Database service for application-level operations.
    
    Provides health checks, connection management, and utilities.
    """
    
    _instance: Optional["DatabaseService"] = None
    
    def __new__(cls) -> "DatabaseService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def health_check(self) -> bool:
        """
        Check database connectivity.
        
        Returns True if database is accessible.
        """
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception:
            return False
    
    async def close(self) -> None:
        """Close all database connections."""
        await engine.dispose()
    
    def get_session(self) -> async_sessionmaker:
        """Get the session factory."""
        return AsyncSessionLocal
