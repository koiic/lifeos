"""T11: scripts/build_tokens.py turns design/tokens.json into CSS custom properties (plan 5.1),
including the typography tokens CR-005 added."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "build_tokens.py"
TOKENS = ROOT / "design" / "tokens.json"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_tokens", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def css_block(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    return css[start : css.index("}", start)]


def test_each_theme_gets_its_font_variation() -> None:
    """CR-005: Night Garden headings use Fraunces "SOFT" 100; Sorbet uses normal."""
    css, ts = load().render(json.loads(TOKENS.read_text()))
    assert "--font-variation-display: normal;" in css_block(css, ":root")
    assert '--font-variation-display: "SOFT" 100;' in css_block(css, ':root[data-theme="dark"]')
    system_dark = css[css.index("@media (prefers-color-scheme: dark)") :]
    assert '--font-variation-display: "SOFT" 100;' in system_dark
    assert "'font-variation-display'," in ts


def test_the_cr_005_shared_tokens_are_emitted() -> None:
    css, _ts = load().render(json.loads(TOKENS.read_text()))
    root = css_block(css, ":root")
    for line in (
        "--font-weight-body: 400;",
        "--font-weight-body-strong: 500;",
        "--font-weight-label: 700;",
        "--size-focus-offset: 2px;",
    ):
        assert line in root


def test_a_theme_without_font_variation_still_renders() -> None:
    tokens = json.loads(TOKENS.read_text())
    for theme in tokens["themes"].values():
        theme.pop("font-variation", None)
    css, _ts = load().render(tokens)
    assert "--font-variation-display" not in css


def test_the_committed_files_are_current() -> None:
    css, ts = load().render(json.loads(TOKENS.read_text()))
    assert (ROOT / "web" / "src" / "ui" / "tokens.css").read_text() == css
    assert (ROOT / "web" / "src" / "ui" / "tokens.ts").read_text() == ts


def test_check_passes_on_the_committed_files() -> None:
    """The done-when command itself: exit 0 when nothing is stale."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_check_fails_and_names_a_stale_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load()
    css, ts = module.render(json.loads(TOKENS.read_text()))
    (tmp_path / "tokens.css").write_text(css.replace("--bg:", "--bg-old:", 1))
    (tmp_path / "tokens.ts").write_text(ts)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "CSS_OUT", tmp_path / "tokens.css")
    monkeypatch.setattr(module, "TS_OUT", tmp_path / "tokens.ts")
    monkeypatch.setattr(sys, "argv", ["build_tokens.py", "--check"])
    assert module.main() == 1
    err = capsys.readouterr().err
    assert "STALE: tokens.css" in err
    assert "tokens.ts" not in err


def test_the_bottom_bar_pads_by_the_safe_area_token() -> None:
    """CR-024 / spec 11: the bar clears the iPhone home indicator via a token, not a raw env()."""
    css, _ts = load().render(json.loads(TOKENS.read_text()))
    assert "--size-safe-bottom: env(safe-area-inset-bottom);" in css_block(css, ":root")
    nav = (ROOT / "web" / "src" / "ui" / "BottomNav" / "BottomNav.module.css").read_text()
    assert "padding-bottom: var(--size-safe-bottom);" in css_block(nav, ".nav")
