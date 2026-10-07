# Life OS

A private, installable web app for cycle tracking, daily check-ins, appointments, medications and
reminders. What to build is in [docs/spec.md](docs/spec.md); how and in what order is in
[docs/plan.md](docs/plan.md); progress is in [docs/plan/PROGRESS.md](docs/plan/PROGRESS.md).

## Local setup

Needs git, Docker (your user able to run it), Node 20+, [uv](https://docs.astral.sh/uv/),
`gitleaks` and `pre-commit`.

```sh
git clone git@github.com:koiic/lifeos.git && cd lifeos
make bootstrap        # uv sync, npm ci, pre-commit install (hooks + commit-msg)
make db               # local PostgreSQL 16 on 127.0.0.1:54320 (infra/docker-compose.dev.yml)
make verify           # every check in plan 6.1
```

## Layout

| Path | Contents |
| --- | --- |
| `server/` | FastAPI app, worker, Alembic migrations, tests (Python 3.12, uv) |
| `web/` | React PWA (TypeScript, Vite), tests |
| `infra/` | Compose files and runbooks |
| `design/` | `tokens.json`, the only source of design values |
| `scripts/` | Verification, ledger, traceability and token tools |
| `docs/` | Spec, plan, ADRs, change requests, task files |

## Useful commands

| Command | What it does |
| --- | --- |
| `make verify-fast` | Format, lint, types, unit tests |
| `make verify` | Everything in plan 6.1, including database tests and migrations |
| `scripts/check_openapi.sh --write` | Regenerate `server/openapi.json` and the web API types |
| `python3 scripts/ledger.py summary` | Build progress |
