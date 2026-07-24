import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.database import Base
from app.config import settings

# Each domain package owns its own models.py — import it here as it's built,
# so Base.metadata is fully populated before autogenerate/migrations run.
from app.auth import models as auth_models  # noqa: F401
from app.workspace import models as workspace_models  # noqa: F401
# from app.catalog import models as catalog_models  # noqa: F401
# from app.discovery import models as discovery_models  # noqa: F401
# from app.reporting import models as reporting_models  # noqa: F401

config = context.config
fileConfig(config.config_file_name)
# Use the sync (psycopg2) URL — alembic runs synchronously
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
