from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# No explicit pool_size/max_overflow — SQLAlchemy's defaults apply
# (pool_size=5, max_overflow=10, so 15 concurrent connections total).
# reporting/service.py's run_full_pipeline and discovery/service.py's
# refresh_saved_sites (MAX_CONCURRENT_SITE_REFRESHES) both size their own
# concurrency against this ceiling — re-derive that math before changing
# either number here.
engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
