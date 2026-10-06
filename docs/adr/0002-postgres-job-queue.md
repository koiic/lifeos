# ADR-0002 — PostgreSQL as the job queue (Procrastinate)

- Status: accepted
- Date: 2026-10-06

## Context
Jobs: outbox relay, reminder dispatch every minute, rebuilds, imports, exports, purges (spec 10.1).

## Decision
Use Procrastinate on the existing PostgreSQL in a `jobs` schema. No Redis.

## Consequences
One stateful service to back up; jobs can be enqueued in the same transaction as the data change.
Throughput needs are tiny (one household).

## Alternatives considered
arq/Celery with Redis (another service to run and back up).
