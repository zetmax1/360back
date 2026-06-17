import asyncio
import logging
from sqlalchemy import select
from app.database import _get_session_factory
from app.models.user import User, UserRole
from app.auth.utils import hash_password
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_superuser():
    if not hasattr(settings, 'ADMIN_EMAIL') or not settings.ADMIN_EMAIL:
        logger.info("ADMIN_EMAIL not set, skipping superuser creation.")
        return
        
    if not hasattr(settings, 'ADMIN_PASSWORD') or not settings.ADMIN_PASSWORD:
        logger.warning("ADMIN_PASSWORD not set but ADMIN_EMAIL is set. Cannot create superuser.")
        return

    factory = _get_session_factory()
    async with factory() as db:
        # Check if admin already exists
        result = await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
        user = result.scalar_one_or_none()
        
        if user:
            logger.info(f"Superuser '{settings.ADMIN_EMAIL}' already exists.")
            return
            
        logger.info(f"Creating default superuser '{settings.ADMIN_EMAIL}'...")
        admin_user = User(
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            role=UserRole.admin,
            is_active=True
        )
        db.add(admin_user)
        await db.commit()
        logger.info("Superuser created successfully.")

if __name__ == "__main__":
    asyncio.run(create_superuser())
