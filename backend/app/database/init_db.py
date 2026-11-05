import asyncio
import logging
from sqlalchemy import select
from app.database.session import engine, async_session_maker, Base
from app.models.entities import User
from app.core.security import get_password_hash
from app.core.config import settings, INSECURE_DEFAULT_DEMO_PASSWORDS

logger = logging.getLogger(__name__)


async def init_db() -> None:
    # 1. Create tables if they do not exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 2. Seed demo auditor user only in development/testing or when non-default password is provided
    if settings.PARTPROOF_ENV == "production" and settings.DEMO_USER_PASSWORD in INSECURE_DEFAULT_DEMO_PASSWORDS:
        logger.warning("Skipping demo user seeding in production: DEMO_USER_PASSWORD uses insecure default.")
        return

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.email == settings.DEMO_USER_EMAIL)
        )
        existing_user = result.scalar_one_or_none()
        
        if not existing_user:
            demo_user = User(
                email=settings.DEMO_USER_EMAIL,
                password_hash=get_password_hash(settings.DEMO_USER_PASSWORD),
                role="admin",
                is_active=True,
            )
            session.add(demo_user)
            await session.commit()
            logger.info(f"Created initial seed user: {settings.DEMO_USER_EMAIL}")
        else:
            logger.debug(f"Seed user already exists: {settings.DEMO_USER_EMAIL}")


if __name__ == "__main__":
    asyncio.run(init_db())
