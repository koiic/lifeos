"""T10: ESLint enforces the web boundaries of plan 4.3 and the inline-style rule of plan 5.2."""

import functools
import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[3] / "web"
NODE = shutil.which("node") or "node"

# Lints every case in one Node process with ESLint's API (one CLI run per case is ~1 s each).
RUNNER = """
import { ESLint } from 'eslint';
const cases = JSON.parse(await new Response(process.stdin).text());
const eslint = new ESLint();
const out = [];
for (const { path, code } of cases) {
  const [result] = await eslint.lintText(code, { filePath: path });
  out.push(result.messages.map((m) => String(m.ruleId)));
}
console.log(JSON.stringify(out));
"""


FEATURE = "src/features/today/Example.tsx"

REJECTED = [
    (FEATURE, "import { X } from '../health/X';\nexport const y = X;\n", "no-restricted-imports"),
    (
        FEATURE,
        "import { X } from '../../features/health/X';\nexport const y = X;\n",
        "no-restricted-imports",
    ),
    (
        FEATURE,
        "import { X } from '../../lib/api/client';\nexport const y = X;\n",
        "no-restricted-imports",
    ),
    (FEATURE, "export const load = () => fetch('/api/v1/me');\n", "no-restricted-globals"),
    (FEATURE, "export const now = () => new Date();\n", "no-restricted-globals"),
    (FEATURE, "export const now = () => Date.now();\n", "no-restricted-globals"),
    (FEATURE, "export const Title = () => <h1>Today</h1>;\n", "react/jsx-no-literals"),
    (
        FEATURE,
        "export const Box = () => <div style={{ color: 'red' }} />;\n",
        "no-restricted-syntax",
    ),
    (
        "src/ui/Card/Card.tsx",
        "export const Box = () => <div style={{ margin: 4 }} />;\n",
        "no-restricted-syntax",
    ),
    (
        "src/lib/dates.ts",
        "export const f = (x: string | null) => x!.length;\n",
        "@typescript-eslint/no-non-null-assertion",
    ),
    (
        "src/lib/api/x.ts",
        "export const f = (x: any): number => x;\n",
        "@typescript-eslint/no-explicit-any",
    ),
]

NESTED = "src/features/today/parts/A.tsx"
DEEP = "src/features/today/a/b/A.tsx"

REJECTED += [
    # Cross-feature imports from nested files (any depth)
    (NESTED, "import { X } from '../../health/X';\nexport const y = X;\n", "no-restricted-imports"),
    (
        DEEP,
        "import { X } from '../../../health/X';\nexport const y = X;\n",
        "no-restricted-imports",
    ),
    # Features use src/ui and lib, not app internals
    (
        FEATURE,
        "import { routes } from '../../app/router';\nexport const y = routes;\n",
        "no-restricted-imports",
    ),
    # Inline style: spread and non-literal values
    (
        FEATURE,
        "const s = { color: 'red' };\nexport const B = () => <div style={{ ...s }} />;\n",
        "no-restricted-syntax",
    ),
    (
        FEATURE,
        "const styles = {};\nexport const B = () => <div style={styles} />;\n",
        "no-restricted-syntax",
    ),
    # User-facing attribute text and strings in JSX expressions
    (FEATURE, "export const B = () => <button aria-label='Close' />;\n", "no-restricted-syntax"),
    (
        FEATURE,
        "export const B = () => <input placeholder='Search notes' />;\n",
        "no-restricted-syntax",
    ),
    (FEATURE, "export const B = () => <abbr title={'Hi'} />;\n", "no-restricted-syntax"),
    (
        FEATURE,
        "export const B = ({ b }: { b: boolean }) => <p>{b ? 'Yes' : 'No'}</p>;\n",
        "no-restricted-syntax",
    ),
    (
        FEATURE,
        "export const B = ({ b }: { b: boolean }) => <p>{b && 'Saved'}</p>;\n",
        "no-restricted-syntax",
    ),
    # Date and fetch in any form
    (FEATURE, "export const d = () => Date();\n", "no-restricted-globals"),
    (FEATURE, "const D = Date;\nexport const d = () => new D();\n", "no-restricted-globals"),
    (FEATURE, "export const d = () => globalThis.Date.now();\n", "no-restricted-properties"),
    (FEATURE, "export const f = () => window.fetch('/x');\n", "no-restricted-properties"),
    (FEATURE, "export const f = () => globalThis.fetch('/x');\n", "no-restricted-properties"),
]

ACCEPTED = [
    (NESTED, "import { TodayScreen } from '../TodayScreen';\nexport const y = TodayScreen;\n"),
    (DEEP, "import { x } from '../../x';\nexport const y = x;\n"),
    (NESTED, "import { copy } from '../../../copy/en-GB';\nexport const y = copy;\n"),
    (FEATURE, "import type { paths } from '../../lib/api';\nexport type P = paths;\n"),
    (
        FEATURE,
        "const f = (o: object) => String(o);\n"
        "export const B = () => <div style={{ '--x': f({ a: 1 }) }} />;\n",
    ),
    (
        FEATURE,
        "export const B = ({ b }: { b: boolean }) => "
        "<div style={b ? { '--x': 1 } : { '--x': 2 }} />;\n",
    ),
    (
        FEATURE,
        "import { copy } from '../../copy/en-GB';\n"
        "export const B = () => <button type='button' aria-label={copy.errors.reload} />;\n",
    ),
    (
        FEATURE,
        "export const B = ({ b }: { b: boolean }) => <p className={b ? 'on' : 'off'} />;\n",
    ),
    (
        FEATURE,
        "import { copy } from '../../copy/en-GB';\n"
        "export const Title = () => <h1>{copy.today.title}</h1>;\n",
    ),
    (FEATURE, "import { api } from '../../lib/api';\nexport const y = api;\n"),
    (FEATURE, "import { Card } from '../../ui/Card';\nexport const y = Card;\n"),
    (FEATURE, "import { formatDay } from '../../lib/dates';\nexport const y = formatDay;\n"),
    (FEATURE, "import { Thing } from './Thing';\nexport const y = Thing;\n"),
    (
        FEATURE,
        "export const Bar = ({ p }: { p: number }) => <div style={{ '--progress': p }} />;\n",
    ),
    ("src/app/App.tsx", "export const Title = () => <h1>Life OS</h1>;\n"),
]


@functools.cache
def lint_all() -> dict[tuple[str, str], list[str]]:
    """Rule ids reported for each (path, code) case, linted as if it lived at `path` in web/."""
    cases = [(path, code) for path, code, _ in REJECTED] + ACCEPTED
    run = subprocess.run(
        [NODE, "--input-type=module", "-e", RUNNER],
        cwd=WEB,
        input=json.dumps([{"path": path, "code": code} for path, code in cases]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    return dict(zip(cases, json.loads(run.stdout), strict=True))


@pytest.mark.parametrize(("path", "code", "rule"), REJECTED)
def test_rejects(path: str, code: str, rule: str) -> None:
    assert rule in lint_all()[(path, code)]


@pytest.mark.parametrize(("path", "code"), ACCEPTED)
def test_accepts(path: str, code: str) -> None:
    rules = lint_all()[(path, code)]
    boundary = {"no-restricted-imports", "no-restricted-globals", "no-restricted-syntax"}
    assert not boundary & set(rules), rules
    assert "react/jsx-no-literals" not in rules
