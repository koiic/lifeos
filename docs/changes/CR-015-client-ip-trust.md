# CR-015 — When the API trusts `CF-Connecting-IP` (per-IP rate limits)

- Raised by: Claude Code during T07
- Date: 2026-10-07
- Status: approved (spec re-sync pending)

## Problem

- Spec 4.1 AUTH-7: "5 failed sign-ins per 15 min per account and per IP, then 15-min lockout".
- Spec 14.3: "The API trusts the client IP only from the `CF-Connecting-IP` header, and only on
  requests that carry the valid Access token."
- Spec 14.3 lists `IP_HMAC_KEY` but no Access settings the API could check a token with
  (`CF_ACCESS_CLIENT_ID`/`SECRET` are Pages Function secrets, sent *to* Access).

"Valid Access token" is not defined for the API. Cloudflare Access adds a signed JWT
(`Cf-Access-Jwt-Assertion`) to requests it lets through; validating it needs the team domain, the
application audience tag and Cloudflare's public keys (fetched from the team domain — an outbound
call the spec does not mention). No task owns this, and T07's per-IP limit depends on it.

## Options

1. **Validate the Access JWT in the API.** New settings `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`
   (14.3); the API fetches and caches the team's signing keys, checks signature (RS256), `aud`,
   `iss`, `exp`; only then reads `CF-Connecting-IP`. Requests without a valid token are refused
   (403) outside local. — impact: 14.3 settings; an outbound HTTPS dependency at start-up; JWT
   checks in `platform/crypto.py`; T15 configures Access.
2. **Network trust instead of token trust.** The API is reachable only through `cloudflared` on
   the Compose network (no published port, 11.1/ADR-0001), so every request already passed Access.
   Outside local the API reads `CF-Connecting-IP` and refuses a request without it (500 problem
   + log); locally it uses the socket address. — impact: 14.3 sentence reworded; T15 must keep the
   API port unpublished (a compose test). No new settings or outbound calls.
3. **Both**: option 2 now, option 1 as hardening in T15. — impact: as option 2, plus option 1's
   work moved to T15.

## Recommendation

Option 2 (or 3 if you want defence in depth later): the tunnel is already the only way in, the
check is simple and testable, and it avoids a runtime dependency on fetching Cloudflare keys.

## Impact if approved

- Spec sections to change: 14.3 (how the client IP is trusted).
- Plan / tasks.json / requirements.json: none (option 3: T15 "done when" gains the JWT check).
- Tokens: none.
- Tasks affected: T07 (blocked until decided), T15.

## Decision (Ibrahim)

Approved by Ibrahim, 2026-10-07: option 2 (network trust: outside local the API reads `CF-Connecting-IP` and refuses requests without it; T15 keeps the API port unpublished). Until the spec is re-synced this CR is the governing text
for the sections it changes.

Still to do (Ibrahim): update the spec, re-export, commit `docs: sync spec vN (CR-015)`.
