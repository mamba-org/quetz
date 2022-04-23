import os

import click
from passlib.hash import pbkdf2_sha256
from sqlmodel import Session, SQLModel, create_engine, select

from .db_models import Credentials


def calculate_hash(value: str) -> str:
    """Calculate hash from value."""
    return pbkdf2_sha256.hash(value)


@click.group()
def _cli():
    pass


@_cli.command("create")
@click.argument("username")
@click.argument("password")
@click.option(
    "--database-url",
    help="The SQLAlchemy URL pointing to the database.",
    default=os.environ.get("QUETZ_SQL_AUTHENTICATOR_DATABASE_URL"),
)
def _create(username: str, password: str, database_url: str) -> None:
    credentials = Credentials(username=username, password=calculate_hash(password))
    with Session(create_engine(database_url)) as session:
        session.add(credentials)
        session.commit()
    click.echo(f"INFO: User '{username}' created successfully.")


@_cli.command("update")
@click.argument("username")
@click.argument("password")
@click.option(
    "--database-url",
    help="The SQLAlchemy URL pointing to the database.",
    default=os.environ.get("QUETZ_SQL_AUTHENTICATOR_DATABASE_URL"),
)
def _update(username: str, password: str, database_url: str) -> None:
    statement = select(Credentials).where(Credentials.username == username)
    with Session(create_engine(database_url)) as session:
        credentials = session.exec(statement).one()
        credentials.password = calculate_hash(password)
        session.commit()
    click.echo(f"INFO: User '{username}' successfully updated.")


@_cli.command("delete")
@click.argument("username")
@click.option(
    "--database-url",
    help="The SQLAlchemy URL pointing to the database.",
    default=os.environ.get("QUETZ_SQL_AUTHENTICATOR_DATABASE_URL"),
)
def _delete(username: str, database_url: str) -> None:
    statement = select(Credentials).where(Credentials.username == username)
    with Session(create_engine(database_url)) as session:
        credentials = session.exec(statement).one()
        session.delete(credentials)
        session.commit()
    click.echo(f"INFO: User '{username}' successfully deleted.")


@_cli.command("reset")
@click.option(
    "--database-url",
    help="The SQLAlchemy URL pointing to the database.",
    default=os.environ.get("QUETZ_SQL_AUTHENTICATOR_DATABASE_URL"),
)
def _reset(database_url: str) -> None:
    engine = create_engine(database_url)
    statement = select(Credentials)
    with Session(engine) as session:
        credentials = list(session.exec(statement))
    click.echo(f"WARNING: Resetting the table will delete {len(credentials)} users.")
    while (
        reset_database := input("Are you sure you want to reset the table? [Y/n]")
    ) not in ("Y", "n"):
        pass
    else:
        if reset_database == "Y":
            SQLModel.metadata.drop_all(engine)
            SQLModel.metadata.create_all(engine)
            click.echo("INFO: Table reset successful.")
        else:
            click.echo("INFO: Table reset aborted.")


if __name__ == "__main__":
    _cli()
