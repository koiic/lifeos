"""A valid lifeos_kek file (CR-011) for deployed-env test apps; not the local dev key."""

import base64

TEST_KEK = "1 " + base64.b64encode(bytes(range(32))).decode()
