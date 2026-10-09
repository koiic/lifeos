"""T14: which subscription endpoints the server will ever POST to (an SSRF allowlist, spec 12.1).

The check is strict so that it cannot disagree with the HTTP client about the host: no user
info, no backslashes, no whitespace or control characters, no explicit port, no empty labels.
"""

import pytest

from app.notify.service import endpoint_allowed


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/QGx",
        "https://api.push.apple.com/3/device/abc",
        "https://wns2-db5p.notify.windows.com/w/?token=AbC%2B",
    ],
)
def test_the_browsers_push_services_are_allowed(endpoint: str) -> None:
    assert endpoint_allowed(endpoint, local=False)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/x",  # not https
        "https://127.0.0.1/x",  # loopback (only the local fake push service, locally)
        "https://localhost/x",
        "https://[::1]/x",
        "https://user:pw@fcm.googleapis.com/x",  # user info
        "https://evil.example\\@fcm.googleapis.com/x",  # parsers disagree on the host
        "https://a@b@fcm.googleapis.com/",
        "https://fcm.googleapis.com\\evil.example/x",
        "https://fcm.googleapis.com:443/x",  # an explicit port
        "https://fcm.googleapis.com:0443/x",
        "https://fcm.googleapis.com:8443/x",
        "https://.push.apple.com/",  # an empty label
        "https://x..push.apple.com/",
        "https://fcm.googleapis.com./x",  # a trailing dot
        "https://fcm.googleapis.com/x\n",  # control characters and whitespace
        "https://fcm.googleapis.com/a b",
        "https://fcm.googleapis.com\t/x",
        "https://fcm.googleapis.com.evil.example/x",
        "https://evil.example/fcm.googleapis.com",
        "https://evil.com%2f.push.apple.com/",  # only ASCII letters, digits and hyphens
        "https://a\u00ad.push.apple.com/",  # a soft hyphen
        "https://\u0435vil.push.apple.com/",  # a Cyrillic letter
        "https://a_b.push.apple.com/",
    ],
)
def test_anything_else_is_refused(endpoint: str) -> None:
    assert not endpoint_allowed(endpoint, local=False)


@pytest.mark.parametrize(
    "endpoint",
    ["http://user:pw@127.0.0.1:9000/x", "http://127.0.0.1:9000\\@evil.example/x"],
)
def test_locally_too_the_loopback_address_must_be_plain(endpoint: str) -> None:
    assert not endpoint_allowed(endpoint, local=True)


def test_locally_the_fake_push_service_is_allowed() -> None:
    assert endpoint_allowed("http://127.0.0.1:9000/s/phone", local=True)
    assert not endpoint_allowed("http://127.0.0.1:9000/s/phone", local=False)
