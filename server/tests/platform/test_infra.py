"""Tests for infrastructure definitions (spec 14.1, 14.2, CR-006, CR-015)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
COMPOSE_FILE = ROOT / "infra" / "docker-compose.yml"
DOCKERFILE = ROOT / "server" / "Dockerfile"


def test_dockerfile_exists_and_configured() -> None:
    assert DOCKERFILE.is_file(), "server/Dockerfile must exist"
    content = DOCKERFILE.read_text()
    # Non-root user
    assert "USER " in content or "useradd" in content or "adduser" in content
    # Python 3.12 base
    assert "python:3.12" in content or "3.12" in content
    # Healthcheck /readyz or entrypoint
    assert "uvicorn" in content


def test_compose_file_services() -> None:
    assert COMPOSE_FILE.is_file(), "infra/docker-compose.yml must exist"
    text = COMPOSE_FILE.read_text()

    # Required services per spec 14.2
    for service in ("cloudflared", "api", "worker", "migrate", "postgres", "backup"):
        assert f"{service}:" in text, f"Missing service {service} in compose file"


def test_compose_api_and_postgres_ports_not_published() -> None:
    """CR-015: Network trust requires api and postgres to not expose ports to the host."""
    text = COMPOSE_FILE.read_text()
    lines = text.splitlines()

    current_service = None
    service_lines: dict[str, list[str]] = {}

    for line in lines:
        stripped = line.strip()
        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            current_service = stripped[:-1]
            service_lines[current_service] = []
        elif current_service and (line.startswith("    ") or stripped == ""):
            service_lines[current_service].append(line)

    # API must not have published ports
    api_content = "\n".join(service_lines.get("api", []))
    assert "ports:" not in api_content, "API must not publish ports to host (CR-015)"

    # Postgres must not have published ports
    pg_content = "\n".join(service_lines.get("postgres", []))
    assert "ports:" not in pg_content, "PostgreSQL must not publish ports outside internal network"


def test_compose_api_read_only_and_secrets() -> None:
    """Spec 14.2: read-only root FS, secrets mounted."""
    text = COMPOSE_FILE.read_text()
    assert "read_only: true" in text or "read_only: true" in text.lower()
    assert "secrets:" in text
    assert "lifeos_kek" in text
