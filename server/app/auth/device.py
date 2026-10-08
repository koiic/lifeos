"""Session device labels "parsed from user agent, e.g. 'iPhone Safari'" (spec 7.2).

Only fixed words come out (a device and a browser from short lists), so nothing from the header
itself is stored or shown.
"""

UNKNOWN = "Unknown device"
MAX_USER_AGENT = 512

# Order matters: the first match wins (iPad before Mac, Android before Linux, Edge before Chrome).
DEVICES = (
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Android", "Android"),
    ("CrOS", "Chromebook"),
    ("Macintosh", "Mac"),
    ("Windows", "Windows"),
    ("Linux", "Linux"),
)
BROWSERS = (
    ("Edg/", "Edge"),
    ("EdgA/", "Edge"),
    ("EdgiOS/", "Edge"),
    ("Firefox/", "Firefox"),
    ("FxiOS/", "Firefox"),
    ("CriOS/", "Chrome"),
    ("Chrome/", "Chrome"),
    ("Version/", "Safari"),
)


def device_label(user_agent: str | None) -> str:
    if not user_agent or len(user_agent) > MAX_USER_AGENT:
        return UNKNOWN
    device = next((label for token, label in DEVICES if token in user_agent), None)
    browser = next((label for token, label in BROWSERS if token in user_agent), None)
    if device is None or browser is None:
        return UNKNOWN
    return f"{device} {browser}"
