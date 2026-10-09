"""Settings (spec 14.3): plain values from the environment, secrets from files (plan 4.6).

`ENV` is required, so a deployment that forgets it fails at start-up instead of running with local
defaults. Secrets are `SecretStr`, so printing or dumping settings never shows them.
"""

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast, get_args
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

Env = Literal["local", "staging", "production"]

SECRETS_DIR = Path("/run/secrets")
LOCAL_APP_ORIGIN = "http://localhost:5173"
# Matches infra/docker-compose.dev.yml; only ever used when ENV=local.
LOCAL_DATABASE_URL = "postgresql://lifeos:lifeos@127.0.0.1:54320/lifeos"
LOCAL_IP_HMAC_KEY = "lifeos-local-development-ip-hmac-key"
VAPID_SECRETS = ("vapid_public_key", "vapid_private_key", "vapid_subject")
ORIGIN = re.compile(r"(?P<scheme>https?)://[A-Za-z0-9.-]+(:\d+)?")
HOSTNAME = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)*")


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
    # lifeos_admin connection for admin endpoints that write (CR-022); without it they answer 503.
    database_admin_write_url: SecretStr | None = None
    # WebAuthn relying party ID (12.3): the app's domain; defaults to APP_ORIGIN's host.
    webauthn_rp_id: str
    # Master key file content (12.2, CR-011); None only in ENV=local (fixed development key).
    lifeos_kek: SecretStr | None = None
    # HMAC key for client IPs (7.2 ip_hash, 12.5, 14.3); None only in ENV=local (fixed dev key).
    ip_hmac_key: SecretStr | None = None
    # Web Push VAPID keys and subject (10.4, 14.3); None only in ENV=local (a pair is generated
    # per process, see platform.crypto.load_vapid).
    vapid_public_key: str | None = None
    vapid_private_key: SecretStr | None = None
    vapid_subject: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _default_rp_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("webauthn_rp_id") and data.get("app_origin"):
            data = data | {"webauthn_rp_id": origin_host(str(data["app_origin"]))}
        return data


def origin_host(origin: str) -> str:
    return (urlsplit(origin).hostname or "").lower()


def rp_id_covers(rp_id: str, origin: str) -> bool:
    """WebAuthn: the RP ID is the origin's host or a parent domain of it (never a bare TLD)."""
    host = origin_host(origin)
    if HOSTNAME.fullmatch(rp_id) is None:
        return False
    return rp_id == host or ("." in rp_id and host.endswith("." + rp_id))


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

    rp_id = environ.get("WEBAUTHN_RP_ID") or origin_host(app_origin)
    if not rp_id_covers(rp_id, app_origin):
        raise ConfigError("WEBAUTHN_RP_ID must be the APP_ORIGIN host or a parent domain of it")

    admin_write_url = read_secret("database_admin_write_url", secrets_dir)
    if admin_write_url is None and local:
        admin_write_url = environ.get("DATABASE_ADMIN_WRITE_URL", database_url)

    kek = read_secret("lifeos_kek", secrets_dir)
    vapid = {name: read_secret(name, secrets_dir) for name in VAPID_SECRETS}
    missing = [name for name, value in vapid.items() if value is None]
    if missing and not local:
        raise ConfigError(f"secret files {', '.join(missing)} are required outside local (10.4)")
    ip_key = read_secret("ip_hmac_key", secrets_dir)
    if ip_key is None and local:
        ip_key = environ.get("IP_HMAC_KEY", LOCAL_IP_HMAC_KEY)

    return Settings(
        env=cast(Env, env),
        app_origin=app_origin,
        database_url=SecretStr(database_url),
        database_owner_url=SecretStr(owner_url) if owner_url else None,
        database_jobs_url=SecretStr(jobs_url) if jobs_url else None,
        database_admin_write_url=SecretStr(admin_write_url) if admin_write_url else None,
        webauthn_rp_id=rp_id,
        lifeos_kek=SecretStr(kek) if kek else None,
        ip_hmac_key=SecretStr(ip_key) if ip_key else None,
        vapid_public_key=vapid["vapid_public_key"],
        vapid_private_key=(
            SecretStr(vapid["vapid_private_key"]) if vapid["vapid_private_key"] else None
        ),
        vapid_subject=vapid["vapid_subject"],
    )
