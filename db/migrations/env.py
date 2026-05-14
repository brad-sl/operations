from logging.config import fileConfig
from sqlalchemy import pool
from alembic import context
from db.models import Base
from db.session import DATABASE_URL
import os
import sys

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    from sqlalchemy.ext.asyncio import create_async_engine

    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = DATABASE_URL

    connectable = create_async_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    def process_revision_directives(context, revision, directives):
        """Called when a migration is executed."""
        def run_cmd():
            def migrate_commands():
                script = context.script
                for cmd in directives:
                    if isinstance(cmd, context.RevisionDirective):
                        if cmd.up_revision:
                            script._upgrade_revisions.add(cmd.up_revision)
                        if cmd.down_revision:
                            script._downgrade_revisions.add(cmd.down_revision)
                    else:
                        cmd()

            migrate_commands()

        context.run_async(run_cmd)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
