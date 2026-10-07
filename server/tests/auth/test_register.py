"""T06: passkey registration (AUTH-1, AUTH-2, AUTH-4; spec 9.2, 12.2, 12.3)."""

import uuid
from datetime import timedelta

import pytest

from app.platform.crypto import Keyring, MasterKey, decrypt, encrypt, unwrap_dek
from tests.auth.conftest import DOMAIN, AuthEnv

pytestmark = pytest.mark.integration

LOCAL_KEYRING = Keyring({1: MasterKey(bytes(32))})


async def test_registration_creates_the_account(env: AuthEnv) -> None:
    token = await env.invite(f"zee{DOMAIN}")
    response = env.register(token)
    assert response.status_code == 201, response.text
    body = response.json()
    user_id = uuid.UUID(body["user_id"])
    assert body["display_name"] == "Zee"

    user = await env.db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    assert user is not None
    assert user["email"] == f"zee{DOMAIN}"
    assert user["kek_version"] == 1
    # The DEK is stored only wrapped, under the KEK with AAD dek:<user_id>.
    dek = unwrap_dek(LOCAL_KEYRING, 1, user["dek_wrapped"], user_id)
    assert decrypt(dek, encrypt(dek, b"x", b"a"), b"a") == b"x"
    assert await env.db.fetchval("SELECT count(*) FROM user_settings WHERE user_id = $1", user_id)
    credential = await env.db.fetchrow(
        "SELECT * FROM webauthn_credentials WHERE user_id = $1", user_id
    )
    assert credential is not None
    assert credential["credential_id"] == env.authenticator.passkeys[0].credential_id
    assert credential["backup_eligible"] is True
    assert (
        await env.db.fetchval(
            "SELECT count(*) FROM sessions WHERE user_id = $1 AND revoked_at IS NULL", user_id
        )
        == 1
    )
    invite = await env.invite_row(token)
    assert invite["used_by"] == user_id
    assert invite["used_at"] == env.clock.now
    # The WebAuthn user handle is the account id.
    assert env.authenticator.passkeys[0].user_handle == user_id.bytes


async def test_ten_recovery_codes_are_shown_once_and_stored_hashed(env: AuthEnv) -> None:
    response = env.register(await env.invite())
    codes = response.json()["recovery_codes"]
    assert len(codes) == 10
    assert len(set(codes)) == 10
    user_id = uuid.UUID(response.json()["user_id"])
    hashes = [
        row["code_hash"]
        for row in await env.db.fetch(
            "SELECT code_hash FROM recovery_codes WHERE user_id = $1", user_id
        )
    ]
    assert len(hashes) == 10
    # argon2id, m = 19 MiB, t = 2, p = 1 (T06 Decisions)
    assert all(h.startswith("$argon2id$v=19$m=19456,t=2,p=1$") for h in hashes)
    assert not set(codes) & set(hashes)


async def test_an_invite_registers_one_account_only(env: AuthEnv) -> None:
    token = await env.invite()
    assert env.register(token).status_code == 201
    second = env.post(
        "/auth/register/options", {"token": token, "name": "Z2", "email": f"z2{DOMAIN}"}
    )
    assert second.status_code == 403


async def test_the_invite_email_must_match(env: AuthEnv) -> None:
    token = await env.invite(f"zee{DOMAIN}")
    response = env.post(
        "/auth/register/options", {"token": token, "name": "Zee", "email": f"other{DOMAIN}"}
    )
    assert response.status_code == 403


async def test_the_invite_email_matches_case_insensitively(env: AuthEnv) -> None:
    token = await env.invite(f"zee{DOMAIN}")
    assert env.register(token, email=f"ZEE{DOMAIN.upper()}").status_code == 201


async def test_an_email_already_registered_is_409(env: AuthEnv) -> None:
    assert env.register(await env.invite()).status_code == 201
    token = await env.invite()
    response = env.post(
        "/auth/register/options", {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"}
    )
    assert response.status_code == 409


async def test_options_require_uv_resident_key_none_attestation_es256_rs256(env: AuthEnv) -> None:
    token = await env.invite()
    options = env.post(
        "/auth/register/options", {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"}
    ).json()
    assert options["rp"]["id"] == "app.test"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["attestation"] == "none"
    assert [p["alg"] for p in options["pubKeyCredParams"]] == [-7, -257]
    assert options["timeout"] == 300000


async def test_a_challenge_is_single_use(env: AuthEnv) -> None:
    token = await env.invite()
    body = {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"}
    options = env.post("/auth/register/options", body).json()
    credential = env.authenticator.create(options)
    assert env.post("/auth/register/verify", body | {"credential": credential}).status_code == 201
    used_at = await env.db.fetchval(
        "SELECT used_at FROM auth_challenges WHERE purpose = 'register' AND invite_id = $1",
        (await env.invite_row(token))["id"],
    )
    assert used_at == env.clock.now
    replay = env.post("/auth/register/verify", body | {"credential": credential})
    assert replay.status_code == 400


async def test_a_failed_verification_still_spends_the_challenge(env: AuthEnv) -> None:
    token = await env.invite()
    body = {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"}
    options = env.post("/auth/register/options", body).json()
    wrong = env.authenticator.create(options, origin="https://evil.test")
    assert env.post("/auth/register/verify", body | {"credential": wrong}).status_code == 400
    good = env.authenticator.create(options)
    assert env.post("/auth/register/verify", body | {"credential": good}).status_code == 400


async def test_the_challenge_is_stored_for_five_minutes(env: AuthEnv) -> None:
    token = await env.invite()
    body = {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"}
    env.post("/auth/register/options", body)
    expires_at = await env.db.fetchval(
        "SELECT expires_at FROM auth_challenges WHERE purpose = 'register' AND invite_id = $1",
        (await env.invite_row(token))["id"],
    )
    assert expires_at == env.clock.now + timedelta(minutes=5)


async def test_a_challenge_works_until_five_minutes(env: AuthEnv) -> None:
    token = await env.invite()
    body = {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"}
    options = env.post("/auth/register/options", body).json()
    env.clock.advance(minutes=4, seconds=59)
    response = env.post(
        "/auth/register/verify", body | {"credential": env.authenticator.create(options)}
    )
    assert response.status_code == 201


async def test_two_registrations_in_flight_on_one_invite_create_one_account(
    env: AuthEnv,
) -> None:
    token = await env.invite()
    first = {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"}
    second = {"token": token, "name": "Zee", "email": f"zee2{DOMAIN}"}
    first_options = env.post("/auth/register/options", first).json()
    second_options = env.post("/auth/register/options", second).json()
    created = env.post(
        "/auth/register/verify", first | {"credential": env.authenticator.create(first_options)}
    )
    assert created.status_code == 201
    late = env.post(
        "/auth/register/verify", second | {"credential": env.authenticator.create(second_options)}
    )
    assert late.status_code == 403
    assert await env.db.fetchval("SELECT count(*) FROM users WHERE email LIKE 'zee%'") == 1
    assert (await env.invite_row(token))["used_by"] == uuid.UUID(created.json()["user_id"])


async def test_rs256_passkeys_register_and_sign_in(env: AuthEnv) -> None:
    response = env.register(await env.invite(), alg="RS256")
    assert response.status_code == 201, response.text
    env.client.cookies.clear()
    assert env.signin().status_code == 200


async def test_other_algorithms_are_rejected(env: AuthEnv) -> None:
    """12.3: ES256 and RS256 only (py_webauthn would also accept EdDSA by default)."""
    response = env.register(await env.invite(), alg="EdDSA")
    assert response.status_code == 400
    assert await env.db.fetchval("SELECT count(*) FROM users WHERE email = $1", f"zee{DOMAIN}") == 0


async def test_a_challenge_expires_after_five_minutes(env: AuthEnv) -> None:
    token = await env.invite()
    body = {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"}
    options = env.post("/auth/register/options", body).json()
    env.clock.advance(minutes=5, seconds=1)
    response = env.post(
        "/auth/register/verify", body | {"credential": env.authenticator.create(options)}
    )
    assert response.status_code == 400
    assert await env.db.fetchval("SELECT count(*) FROM users WHERE email = $1", f"zee{DOMAIN}") == 0


async def test_user_verification_is_required(env: AuthEnv) -> None:
    env.authenticator.user_verification = False
    response = env.register(await env.invite())
    assert response.status_code == 400
    assert await env.db.fetchval("SELECT count(*) FROM users WHERE email = $1", f"zee{DOMAIN}") == 0


@pytest.mark.parametrize(
    "create", [{"origin": "https://evil.test"}, {"rp_id": "evil.test"}], ids=["origin", "rp-id"]
)
async def test_wrong_origin_or_rp_id_is_rejected(env: AuthEnv, create: dict[str, str]) -> None:
    response = env.register(await env.invite(), **create)
    assert response.status_code == 400


async def test_verify_rechecks_the_invite(env: AuthEnv) -> None:
    token = await env.invite()
    body = {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"}
    options = env.post("/auth/register/options", body).json()
    await env.db.execute(
        "UPDATE invites SET revoked_at = now() WHERE id = $1", (await env.invite_row(token))["id"]
    )
    response = env.post(
        "/auth/register/verify", body | {"credential": env.authenticator.create(options)}
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("field", "value"),
    [("name", ""), ("name", "x" * 101), ("email", "not-an-email"), ("email", "a@b")],
)
async def test_name_and_email_are_validated(env: AuthEnv, field: str, value: str) -> None:
    token = await env.invite()
    body = {"token": token, "name": "Zee", "email": f"zee{DOMAIN}"} | {field: value}
    assert env.post("/auth/register/options", body).status_code == 422


async def test_a_100_character_name_is_accepted(env: AuthEnv) -> None:
    assert env.register(await env.invite(), name="x" * 100).json()["display_name"] == "x" * 100


async def test_emails_are_cleaned(env: AuthEnv) -> None:
    """9.4 strings: trimmed, control characters stripped."""
    response = env.register(await env.invite(), email=f" zee\u0007{DOMAIN} ")
    assert response.status_code == 201
    user_id = uuid.UUID(response.json()["user_id"])
    assert await env.db.fetchval("SELECT email FROM users WHERE id = $1", user_id) == f"zee{DOMAIN}"


async def test_names_are_trimmed_and_normalised(env: AuthEnv) -> None:
    decomposed = "Ze" + chr(0x301) + "e"  # e + combining acute
    response = env.register(await env.invite(), name=f"  {decomposed}{chr(7)} ")
    assert response.json()["display_name"] == "Z" + chr(0xE9) + "e"  # precomposed é (NFC)
