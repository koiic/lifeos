# ADR-0003 — Health values only inside encrypted payload columns

- Status: accepted
- Date: 2026-10-06

## Context
A database leak must not reveal period dates, symptoms, medications or notes (spec 12.1).

## Decision
Per-user data keys wrapped by a master key; AES-256-GCM per field with AAD binding table, column,
row and user (spec 7.1, 12.2). Period days are flow values inside the encrypted daily log, not a
plaintext table. Only scheduling and sorting columns stay plaintext.

## Consequences
The cycle engine decrypts in memory (a few thousand rows at most). Server-side search over health
values is not possible; not needed for the MVP. The operator can still decrypt with the master key
(spec 12.1); client-held keys are a post-MVP option.

## Alternatives considered
Full-disk encryption only (does not protect dumps or backups); client-side encryption (too large for MVP).
