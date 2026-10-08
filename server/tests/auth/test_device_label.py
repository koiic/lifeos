"""T08: session device labels "parsed from user agent, e.g. 'iPhone Safari'" (spec 7.2)."""

import pytest

from app.auth.device import device_label

IPHONE_SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
IPHONE_CHROME = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) CriOS/126.0.6478.54 Mobile/15E148 Safari/604.1"
)
IPAD_SAFARI = (
    "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)
ANDROID_CHROME = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
)
ANDROID_FIREFOX = "Mozilla/5.0 (Android 14; Mobile; rv:127.0) Gecko/127.0 Firefox/127.0"
MAC_SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)
MAC_FIREFOX = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:127.0) Gecko/20100101 Firefox/127.0"
WINDOWS_EDGE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
)
WINDOWS_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
LINUX_FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
CHROMEBOOK = (
    "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
ANDROID_EDGE = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36 EdgA/126.0.0.0"
)
IPHONE_FIREFOX = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) FxiOS/127.0 Mobile/15E148 Safari/605.1.15"
)


@pytest.mark.parametrize(
    ("user_agent", "label"),
    [
        (IPHONE_SAFARI, "iPhone Safari"),
        (IPHONE_CHROME, "iPhone Chrome"),
        (IPAD_SAFARI, "iPad Safari"),
        (ANDROID_CHROME, "Android Chrome"),
        (ANDROID_FIREFOX, "Android Firefox"),
        (MAC_SAFARI, "Mac Safari"),
        (MAC_FIREFOX, "Mac Firefox"),
        (WINDOWS_EDGE, "Windows Edge"),
        (WINDOWS_CHROME, "Windows Chrome"),
        (LINUX_FIREFOX, "Linux Firefox"),
        (CHROMEBOOK, "Chromebook Chrome"),
        (ANDROID_EDGE, "Android Edge"),
        (IPHONE_FIREFOX, "iPhone Firefox"),
    ],
)
def test_known_user_agents(user_agent: str, label: str) -> None:
    assert device_label(user_agent) == label


@pytest.mark.parametrize("user_agent", [None, "", "curl/8.0", "x" * 2000, "<script>"])
def test_anything_else_is_an_unknown_device(user_agent: str | None) -> None:
    assert device_label(user_agent) == "Unknown device"


def test_the_label_never_contains_the_raw_user_agent() -> None:
    """Only fixed words come out, so nothing from the header is stored."""
    assert device_label(IPHONE_SAFARI + " evil-tracking-id-123") == "iPhone Safari"
