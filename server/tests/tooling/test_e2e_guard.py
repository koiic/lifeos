"""T12: the e2e stack helpers (fresh database, test invites) can only touch a local `_e2e`
database — never a remote server or a real database (spec 14.4)."""

import pytest

from tests.e2e.guard import NotAnE2eDatabase, e2e_database, same_server

LOCAL_E2E = "postgresql://lifeos:lifeos@127.0.0.1:54320/lifeos_e2e"
LOCAL_BASE = "postgresql://lifeos:lifeos@127.0.0.1:54320/lifeos"


def test_a_local_e2e_database_is_accepted() -> None:
    assert e2e_database(LOCAL_E2E) == "lifeos_e2e"
    assert e2e_database("postgresql+asyncpg://u:p@localhost:5432/x_e2e") == "x_e2e"
    same_server(LOCAL_BASE, LOCAL_E2E)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://u:p@db.staging.example:5432/lifeos_e2e",
        "postgresql://lifeos:lifeos@127.0.0.1:54320/lifeos",
        'postgresql://lifeos:lifeos@127.0.0.1:54320/x"; DROP DATABASE lifeos; --_e2e',
        "postgresql://lifeos:lifeos@127.0.0.1:54320/Lifeos_E2E",
    ],
)
def test_anything_else_is_refused(dsn: str) -> None:
    with pytest.raises(NotAnE2eDatabase):
        e2e_database(dsn)


def test_the_maintenance_connection_must_be_the_same_local_server() -> None:
    with pytest.raises(NotAnE2eDatabase):
        same_server("postgresql://u:p@db.staging.example:5432/lifeos", LOCAL_E2E)
    with pytest.raises(NotAnE2eDatabase):
        same_server("postgresql://lifeos:lifeos@127.0.0.1:5432/lifeos", LOCAL_E2E)
