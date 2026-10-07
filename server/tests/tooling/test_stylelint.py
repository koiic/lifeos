"""T01: stylelint makes it impossible to ship a design value from outside the tokens (plan 5.2)."""

import functools
import json
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[3] / "web"
STYLELINT = WEB / "node_modules" / ".bin" / "stylelint"

ACCEPTED = [
    "color: var(--ink)",
    "background-color: var(--surface)",
    "margin: var(--space-4)",
    "margin: 0",
    "padding: var(--space-2) var(--space-4)",
    "margin-top: calc(-1 * var(--space-2))",
    "gap: calc(var(--space-2) * 2)",
    "border-radius: var(--radius-card)",
    "border-top-left-radius: var(--radius-card)",
    "font-family: var(--font-body)",
    "box-shadow: var(--shadow-sticker)",
    "transition-property: opacity",
    "transition-duration: var(--motion-duration-fast)",
    "transition-timing-function: var(--motion-ease-out)",
    "transition-delay: 0s",
    "animation-name: wiggle",
    "animation-duration: var(--motion-duration-base)",
    "border: var(--size-focus-ring) solid var(--border-strong)",
]

REJECTED = [
    # Raw colours (hex, named, colour functions)
    "color: #fff",
    "background-color: red",
    "color: rgb(0 0 0)",
    "color: color(display-p3 1 0 0)",
    "color: color-mix(in srgb, var(--ink) 50%, var(--surface))",
    # Raw spacing, radius, shadow, font
    "margin: 12px",
    "padding-inline: 8px",
    "gap: 4px",
    "border-radius: 8px",
    "border-top-left-radius: 8px",
    "box-shadow: 0 1px 2px var(--ink)",
    "font-family: Arial, sans-serif",
    # Functions and fallbacks must not smuggle raw values
    "margin: calc(12px + 1px)",
    "margin: max(12px, 1px)",
    "border-radius: min(8px)",
    "transition-duration: calc(200ms)",
    "font-family: var(--font-body, Arial)",
    # transition*, animation* and the font shorthand
    "transition-duration: 200ms",
    "transition-delay: 150ms",
    "transition: opacity 200ms ease-in",
    "animation: spin 300ms linear",
    "font: 16px/1.5 Arial, sans-serif",
]


@functools.cache
def problems_by_declaration() -> dict[str, list[str]]:
    """Lint every case in one stylelint run; map each declaration to the rules it broke."""
    cases = ACCEPTED + REJECTED
    # Rule i occupies lines 4i+1..4i+4 (blank line last), so its declaration is on line 4i+2.
    css = "".join(f".c{i} {{\n  {d};\n}}\n\n" for i, d in enumerate(cases)).rstrip() + "\n"
    run = subprocess.run(
        [str(STYLELINT), "--stdin-filename", "src/ui/Probe/Probe.module.css", "-f", "json"],
        cwd=WEB,
        input=css,
        capture_output=True,
        text=True,
        check=False,
    )
    results = json.loads(run.stdout or run.stderr)
    found: dict[str, list[str]] = {d: [] for d in cases}
    for warning in results[0]["warnings"]:
        assert (warning["line"] - 2) % 4 == 0, f"warning off a declaration line: {warning}"
        found[cases[(warning["line"] - 2) // 4]].append(warning["rule"])
    return found


@pytest.mark.parametrize("declaration", ACCEPTED)
def test_accepts_token_values(declaration: str) -> None:
    assert problems_by_declaration()[declaration] == []


@pytest.mark.parametrize("declaration", REJECTED)
def test_rejects_raw_values(declaration: str) -> None:
    assert problems_by_declaration()[declaration] != [], f"stylelint accepted: {declaration}"
