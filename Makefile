# Life OS — verification contract (plan section 6.1).
# The target NAMES and what they check are fixed by the plan. T01 makes every recipe work;
# later tasks may add steps to a recipe but never remove one or weaken a threshold.
# check_migrations.sh, check_openapi.sh, check_coverage.py and ensure_db.sh are created in T01 and
# extended by later tasks. Created by the tasks that own them: check_external_origins.sh and
# scan_images.sh (T16), zap_baseline.sh (T50), npm "lighthouse" script (T13), npm "test:e2e"
# script (first task with Playwright tests: T11, visual snapshots of the Ladle stories).

.PHONY: verify verify-fast verify-e2e verify-full fmt-check lint types arch test-server test-web \
        migrations api-contract tokens trace secrets dev bootstrap db

verify: fmt-check lint types arch test-server test-web migrations api-contract tokens trace secrets
	@echo "verify: all checks passed"

verify-fast: fmt-check lint types tokens
	cd server && uv run pytest -q -m "not integration"
	cd web && npm run test:unit -- --run

verify-e2e:
	cd web && npm run test:e2e

verify-full: verify verify-e2e
	cd web && npm run lighthouse
	./scripts/zap_baseline.sh
	cd server && uv run pip-audit
	cd web && npm audit --audit-level=high
	./scripts/scan_images.sh
	./scripts/check_external_origins.sh

fmt-check:
	cd server && uv run ruff format --check .
	cd web && npx --no-install prettier --check .

lint:
	cd server && uv run ruff check .
	cd web && npx --no-install eslint . --max-warnings 0
	cd web && npx --no-install stylelint "src/**/*.css" --max-warnings 0

types:
	cd server && uv run mypy --strict app
	cd web && npx --no-install tsc --noEmit

arch:
	cd server && uv run lint-imports

test-server: db
	cd server && uv run pytest -q --cov=app --cov-config=.coveragerc --cov-report=term --cov-report=json
	python3 scripts/check_coverage.py server/coverage.json

test-web:
	cd web && npm run test:unit -- --run --coverage
	cd web && npm run build && npx --no-install size-limit

migrations: db
	./scripts/check_migrations.sh

api-contract:
	./scripts/check_openapi.sh

tokens:
	python3 scripts/build_tokens.py --check
	python3 scripts/check_contrast.py
	python3 scripts/build_icons.py --check

trace:
	python3 scripts/trace.py

secrets:
	gitleaks git --no-banner --redact
	gitleaks dir --no-banner --redact .

db:
	./scripts/ensure_db.sh

bootstrap:
	cd server && uv sync
	cd web && npm ci
	pre-commit install

dev:
	docker compose -f infra/docker-compose.dev.yml up -d postgres
	cd server && ENV=local uv run alembic upgrade head
	@echo "run: (cd server && ENV=local uv run uvicorn app.main:app --reload) and (cd web && npm run dev)"
