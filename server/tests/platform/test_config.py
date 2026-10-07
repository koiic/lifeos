"""T02: settings come from the environment, secrets from files (spec 14.3, plan 4.6)."""

from pathlib import Path

import pytest

from app.platform.config import ConfigError, load_settings

LOCAL = {"ENV": "local"}
DEPLOYED = ["staging", "production"]


def test_env_is_required(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="ENV"):
        load_settings({}, secrets_dir=tmp_path)


def test_local_defaults_need_no_other_configuration(tmp_path: Path) -> None:
    settings = load_settings(LOCAL, secrets_dir=tmp_path)
    assert settings.env == "local"
    assert settings.app_origin == "http://localhost:5173"
    assert settings.database_url.get_secret_value().startswith("postgresql://")


def test_local_accepts_database_url_from_the_environment(tmp_path: Path) -> None:
    settings = load_settings(LOCAL | {"DATABASE_URL": "postgresql://u:p@db/x"}, tmp_path)
    assert settings.database_url.get_secret_value() == "postgresql://u:p@db/x"


@pytest.mark.parametrize("env", DEPLOYED)
def test_deployed_envs_read_the_database_url_from_the_secret_file(env: str, tmp_path: Path) -> None:
    (tmp_path / "database_url").write_text("postgresql://app:s3cret@postgres/lifeos\n")
    settings = load_settings(
        {"ENV": env, "APP_ORIGIN": "https://app.example.com"}, secrets_dir=tmp_path
    )
    assert settings.env == env
    assert settings.database_url.get_secret_value() == "postgresql://app:s3cret@postgres/lifeos"


@pytest.mark.parametrize("env", DEPLOYED)
def test_deployed_envs_ignore_secrets_in_the_environment(env: str, tmp_path: Path) -> None:
    environ = {
        "ENV": env,
        "APP_ORIGIN": "https://app.example.com",
        "DATABASE_URL": "postgresql://from-env/x",
    }
    with pytest.raises(ConfigError, match="database_url"):
        load_settings(environ, secrets_dir=tmp_path)


@pytest.mark.parametrize("env", DEPLOYED)
@pytest.mark.parametrize("content", ["", "\n", "   \n"])
def test_an_empty_secret_file_counts_as_missing(env: str, content: str, tmp_path: Path) -> None:
    (tmp_path / "database_url").write_text(content)
    with pytest.raises(ConfigError, match="database_url"):
        load_settings({"ENV": env, "APP_ORIGIN": "https://app.example.com"}, tmp_path)


def test_deployed_envs_require_app_origin(tmp_path: Path) -> None:
    (tmp_path / "database_url").write_text("postgresql://app:pw@postgres/lifeos")
    with pytest.raises(ConfigError, match="APP_ORIGIN"):
        load_settings({"ENV": "production"}, secrets_dir=tmp_path)


@pytest.mark.parametrize("env", DEPLOYED)
def test_deployed_envs_require_https(env: str, tmp_path: Path) -> None:
    (tmp_path / "database_url").write_text("postgresql://app:pw@postgres/lifeos")
    with pytest.raises(ConfigError, match="https"):
        load_settings({"ENV": env, "APP_ORIGIN": "http://app.example.com"}, tmp_path)


def test_unknown_env_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="ENV"):
        load_settings({"ENV": "dev"}, secrets_dir=tmp_path)


@pytest.mark.parametrize(
    "origin",
    [
        "https://app.example.com/",
        "https://app.example.com/path",
        "https://app.example.com\n",
        "app.example.com",
        "ftp://x.y",
    ],
)
def test_app_origin_must_be_a_bare_origin(origin: str, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="APP_ORIGIN"):
        load_settings(LOCAL | {"APP_ORIGIN": origin}, secrets_dir=tmp_path)


def test_settings_never_print_secrets(tmp_path: Path) -> None:
    (tmp_path / "database_url").write_text("postgresql://app:s3cret@postgres/lifeos")
    settings = load_settings({"ENV": "production", "APP_ORIGIN": "https://a.example"}, tmp_path)
    for text in (repr(settings), str(settings), str(settings.model_dump())):
        assert "s3cret" not in text


def test_owner_url_defaults_to_the_database_url_locally(tmp_path: Path) -> None:
    settings = load_settings(LOCAL | {"DATABASE_URL": "postgresql://u:p@db/x"}, tmp_path)
    assert settings.database_owner_url is not None
    assert settings.database_owner_url.get_secret_value() == "postgresql://u:p@db/x"


@pytest.mark.parametrize("env", DEPLOYED)
def test_owner_url_comes_from_its_secret_file_when_present(env: str, tmp_path: Path) -> None:
    (tmp_path / "database_url").write_text("postgresql://app:pw@postgres/lifeos")
    (tmp_path / "database_owner_url").write_text("postgresql://owner:s3cret@postgres/lifeos")
    settings = load_settings({"ENV": env, "APP_ORIGIN": "https://a.example"}, tmp_path)
    assert settings.database_owner_url is not None
    assert settings.database_owner_url.get_secret_value().startswith("postgresql://owner:")
    assert "s3cret" not in repr(settings)


@pytest.mark.parametrize("env", DEPLOYED)
def test_owner_url_is_optional_for_the_api(env: str, tmp_path: Path) -> None:
    (tmp_path / "database_url").write_text("postgresql://app:pw@postgres/lifeos")
    settings = load_settings({"ENV": env, "APP_ORIGIN": "https://a.example"}, tmp_path)
    assert settings.database_owner_url is None


def test_local_owner_url_can_be_set_in_the_environment(tmp_path: Path) -> None:
    environ = LOCAL | {
        "DATABASE_URL": "postgresql://app:p@db/x",
        "DATABASE_OWNER_URL": "postgresql://owner:p@db/x",
    }
    settings = load_settings(environ, tmp_path)
    assert settings.database_owner_url is not None
    assert settings.database_owner_url.get_secret_value() == "postgresql://owner:p@db/x"


def test_jobs_url_defaults_to_the_database_url_locally(tmp_path: Path) -> None:
    settings = load_settings(LOCAL | {"DATABASE_URL": "postgresql://u:p@db/x"}, tmp_path)
    assert settings.database_jobs_url is not None
    assert settings.database_jobs_url.get_secret_value() == "postgresql://u:p@db/x"


@pytest.mark.parametrize("env", DEPLOYED)
def test_jobs_url_comes_from_its_secret_file(env: str, tmp_path: Path) -> None:
    (tmp_path / "database_url").write_text("postgresql://app:pw@postgres/lifeos")
    (tmp_path / "database_jobs_url").write_text("postgresql://jobs:s3cret@postgres/lifeos")
    settings = load_settings({"ENV": env, "APP_ORIGIN": "https://a.example"}, tmp_path)
    assert settings.database_jobs_url is not None
    assert settings.database_jobs_url.get_secret_value().startswith("postgresql://jobs:")
    assert "s3cret" not in repr(settings)


@pytest.mark.parametrize("env", DEPLOYED)
def test_jobs_url_is_optional_for_the_api(env: str, tmp_path: Path) -> None:
    (tmp_path / "database_url").write_text("postgresql://app:pw@postgres/lifeos")
    settings = load_settings({"ENV": env, "APP_ORIGIN": "https://a.example"}, tmp_path)
    assert settings.database_jobs_url is None
