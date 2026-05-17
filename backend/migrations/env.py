import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Make backend/ importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import app to register all models with SQLAlchemy metadata
from app.extensions import db
from app import create_app

flask_app = create_app(os.getenv('FLASK_ENV', 'development'))
target_metadata = db.metadata


def get_url() -> str:
    url = os.getenv('DATABASE_URL', config.get_main_option('sqlalchemy.url', ''))
    # SQLAlchemy 2.x requires postgresql:// not postgres://
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg['sqlalchemy.url'] = get_url()

    connectable = engine_from_config(
        cfg,
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


with flask_app.app_context():
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
