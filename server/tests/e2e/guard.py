"""Test-only: the e2e helpers touch only a local database whose name ends in `_e2e`."""

import re
from urllib.parse import urlsplit

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
E2E_NAME = re.compile(r"[a-z0-9_]+_e2e")


class NotAnE2eDatabase(SystemExit):
    pass


def e2e_database(dsn: str) -> str:
    """The database name of `dsn`, if it is a local `_e2e` database; otherwise refuse."""
    parts = urlsplit(dsn)
    if parts.hostname not in LOCAL_HOSTS:
        raise NotAnE2eDatabase(f"refusing a non-local database host: {parts.hostname}")
    name = parts.path.lstrip("/")
    if E2E_NAME.fullmatch(name) is None:
        raise NotAnE2eDatabase("refusing a database whose name is not like lifeos_e2e")
    return name


def same_server(base_dsn: str, e2e_dsn: str) -> None:
    """The maintenance connection must be the same local server as the e2e database."""
    base, e2e = urlsplit(base_dsn), urlsplit(e2e_dsn)
    if base.hostname not in LOCAL_HOSTS:
        raise NotAnE2eDatabase(f"refusing a non-local database host: {base.hostname}")
    if (base.hostname, base.port) != (e2e.hostname, e2e.port):
        raise NotAnE2eDatabase("the base and e2e databases must be on the same local server")
