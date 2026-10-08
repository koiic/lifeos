"""T11: the self-hosted fonts follow spec 5.4 (Fontsource WOFF2, Latin subset, font-display swap)
and never load from another origin (12.4)."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "web"
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text())
FONTS = (WEB / "src" / "ui" / "fonts.css").read_text()
FACES = FONTS.split("@font-face {")[1:]
LATIN_FILE = re.compile(
    r"^\.\./\.\./node_modules/@fontsource-variable/[a-z-]+/files/[a-z-]+-latin-[a-z]+-normal\.woff2$"
)


def family(face: str) -> str:
    match = re.search(r"font-family:\s*['\"]?([^'\";]+)['\"]?;", face)
    assert match is not None
    return match.group(1)


def token_families() -> set[str]:
    """The first family of every theme's font tokens (the rest are system fallbacks)."""
    return {
        stack.split(",")[0].strip().strip("'\"")
        for theme in TOKENS["themes"].values()
        for stack in theme["font"].values()
    }


def test_the_three_families_the_font_tokens_name() -> None:
    assert token_families() == {"Bricolage Grotesque", "DM Sans", "Fraunces"}
    assert sorted(family(face) for face in FACES) == sorted(token_families())


def test_every_face_swaps_and_loads_one_local_latin_woff2() -> None:
    assert len(FACES) == 3
    for face in FACES:
        assert "font-display: swap;" in face
        urls = re.findall(r"url\(['\"]([^'\"]+)['\"]\)", face)
        assert len(urls) == 1
        assert LATIN_FILE.match(urls[0]), urls[0]
        assert (WEB / "src" / "ui" / urls[0]).resolve().is_file(), urls[0]


def test_fraunces_uses_the_build_with_the_soft_axis() -> None:
    [fraunces] = [face for face in FACES if family(face) == "Fraunces"]
    assert "fraunces-latin-soft-normal.woff2" in fraunces


def test_no_font_comes_from_another_origin() -> None:
    assert not re.search(r"https?:", FONTS)
