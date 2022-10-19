import click
from passlib.hash import pbkdf2_sha256

from quetz.database import get_db_manager

from .db_models import Credentials


def calculate_hash(value: str) -> str:
    """Calculate hash from value."""
    return pbkdf2_sha256.hash(value)


@click.group()
def _cli():
    """
    Manage the credentials of the SQL Authenticator plugin.
    The `QUETZ_CONFIG_FILE` environment variable must be set to the path of the QUETZ
    configuration file, e.g. `/home/user/quetz_server/config.toml`.

    If the Database URL specified in the configuration file is a relative path to a
    SQLite database, you need to make sure to run the CLI from the directory
    that that path is relative to.
    """
    pass


@_cli.command("create")
@click.argument("username")
@click.argument("password")
def _create(username: str, password: str) -> None:
    credentials = Credentials(username=username, password=calculate_hash(password))
    with get_db_manager() as db:
        db.add(credentials)
        db.commit()
    click.echo(f"INFO: User '{username}' created successfully.")


@_cli.command("update")
@click.argument("username")
@click.argument("password")
def _update(username: str, password: str) -> None:
    with get_db_manager() as db:
        credentials = (
            db.query(Credentials).filter(Credentials.username == username).one_or_none()
        )
        if credentials is None:
            raise click.ClickException(f"ERROR: User '{username}' not found.")
        credentials.password = calculate_hash(password)
        db.commit()
    click.echo(f"INFO: User '{username}' successfully updated.")


@_cli.command("delete")
@click.argument("username")
def _delete(username: str) -> None:
    with get_db_manager() as db:
        credentials = (
            db.query(Credentials).filter(Credentials.username == username).one_or_none()
        )
        if credentials is None:
            raise click.ClickException(f"ERROR: User '{username}' not found.")
        db.delete(credentials)
        db.commit()
    click.echo(f"INFO: User '{username}' successfully deleted.")


@_cli.command("reset")
def _reset() -> None:
    with get_db_manager() as db:
        credentials_count = db.query(Credentials).count()
    click.echo(f"WARNING: Resetting the table will delete {credentials_count} users.")
    if click.confirm("Are you sure you want to reset the table? [Y/n]"):
        with get_db_manager() as db:
            db.query(Credentials).delete()
            db.commit()
        click.echo("INFO: Table reset successful.")
    else:
        click.echo("INFO: Table reset aborted.")


if __name__ == "__main__":
    _cli()
