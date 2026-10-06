# ADR-0001 — Hybrid hosting: Cloudflare Pages + VPS behind Cloudflare Tunnel

- Status: accepted
- Date: 2026-10-06

## Context

Reminders need a job every minute (spec 10). Vercel Hobby allows cron only once per day with
±59 min precision; Vercel Pro is paid and would remove the long-running worker. Ibrahim wants to
start on Cloudflare or Vercel.

## Decision

- Static PWA on Cloudflare Pages (`web/`).
- Same-origin API: Pages Function `web/functions/api/[[path]].ts` forwards `/api/*` to `ORIGIN_URL`
  with Cloudflare Access service-token headers. It adds no logic.
- FastAPI, Procrastinate worker and PostgreSQL on one VPS with Docker Compose; `cloudflared` is the
  only path in. No public web ports on the VPS.
- Static security headers in `web/public/_headers`; API headers set by FastAPI middleware.

## Consequences

- One browser origin, so cookies, CSP and WebAuthn work unchanged.
- The production domain must be on Cloudflare before Zee registers a passkey (plan 2.2).
- Pages Function CPU limits are irrelevant for a pass-through proxy; request bodies (imports up to
  20 MB) are within limits.

## Alternatives considered

Vercel Hobby (daily cron), Vercel Pro (cost, job redesign), everything on the VPS with Caddy.
