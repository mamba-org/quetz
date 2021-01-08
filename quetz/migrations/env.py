import os

from alembic import context
from alembic.config import Config as AlembicConfig
from sqlalchemy import engine_from_config, pool

from quetz.config import Config
from quetz.db_models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config: AlembicConfig = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():

    db_path = config.get_main_option("sqlalchemy.url")
    if not db_path:
        config_path = context.get_x_argument(as_dictionary=True).get('quetzConfig')
        deployment_path = os.path.split(config_path)[0]
        quetz_config = Config(config_path)
        db_path = quetz_config.sqlalchemy_database_url
        abs_path = os.path.abspath(deployment_path)

        db_path = db_path.replace("sqlite:///.", f"sqlite:///{abs_path}")
    return db_path


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = config.attributes.get('connection', None)

    if connectable is None:

        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
