"""Settings (spec 14.3): plain values from the environment, secrets from files (plan 4.6).

`ENV` is required, so a deployment that forgets it fails at start-up instead of running with local
defaults. Secrets are `SecretStr`, so printing or dumping settings never shows them.
"""

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast, get_args

from pydantic import BaseModel, ConfigDict, SecretStr

Env = Literal["local", "staging", "production"]

SECRETS_DIR = Path("/run/secrets")
LOCAL_APP_ORIGIN = "http://localhost:5173"
# Matches infra/docker-compose.dev.yml; only ever used when ENV=local.
LOCAL_DATABASE_URL = "postgresql://lifeos:lifeos@127.0.0.1:54320/lifeos"
ORIGIN = re.compile(r"(?P<scheme>https?)://[A-Za-z0-9.-]+(:\d+)?")


class ConfigError(ValueError):
    """Configuration is missing or invalid; the process must not start."""


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    env: Env
    app_origin: str
    database_url: SecretStr
    # lifeos_owner connection for migrations (CR-003, 14.3); only the migrate container has it.
    database_owner_url: SecretStr | None = None
    # lifeos_jobs connection for the worker (CR-003, 14.3); the API does not need it.
    database_jobs_url: SecretStr | None = None


def read_secret(name: str, secrets_dir: Path) -> str | None:
    """A secret file's content, or None when the file is missing or blank."""
    path = secrets_dir / name
    value = path.read_text().strip() if path.is_file() else ""
    return value or None


def load_settings(
    environ: Mapping[str, str] | None = None, secrets_dir: Path = SECRETS_DIR
) -> Settings:
    environ = os.environ if environ is None else environ

    env = environ.get("ENV")
    if env not in get_args(Env):
        raise ConfigError(f"ENV is required and must be one of {', '.join(get_args(Env))}")
    local = env == "local"

    app_origin = environ.get("APP_ORIGIN") or (LOCAL_APP_ORIGIN if local else None)
    if app_origin is None:
        raise ConfigError("APP_ORIGIN is required outside local")
    origin = ORIGIN.fullmatch(app_origin)
    if origin is None:
        raise ConfigError("APP_ORIGIN must be a bare origin such as https://app.example.com")
    if not local and origin["scheme"] != "https":
        raise ConfigError("APP_ORIGIN must use https outside local")

    database_url = read_secret("database_url", secrets_dir)
    if database_url is None and local:
        database_url = environ.get("DATABASE_URL", LOCAL_DATABASE_URL)
    if database_url is None:
        raise ConfigError(f"secret file {secrets_dir / 'database_url'} is required outside local")

    owner_url = read_secret("database_owner_url", secrets_dir)
    if owner_url is None and local:
        owner_url = environ.get("DATABASE_OWNER_URL", database_url)
    jobs_url = read_secret("database_jobs_url", secrets_dir)
    if jobs_url is None and local:
        jobs_url = environ.get("DATABASE_JOBS_URL", database_url)

    return Settings(
        env=cast(Env, env),
        app_origin=app_origin,
        database_url=SecretStr(database_url),
        database_owner_url=SecretStr(owner_url) if owner_url else None,
        database_jobs_url=SecretStr(jobs_url) if jobs_url else None,
    )
