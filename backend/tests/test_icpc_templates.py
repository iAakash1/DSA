"""The contest templates must actually compile.

A template library that looks right but does not build is worse than none: it
fails at the one moment it exists for. The whole library is compiled as a
single translation unit, which is how it is used — the templates are pasted
into one file during a contest.

Skipped (never silently passed) when no C++ compiler is present.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.icpc.templates import TEMPLATES, TEMPLATES_BY_SLUG, template_detail

COMPILER = shutil.which("g++") or shutil.which("clang++")

pytestmark = pytest.mark.skipif(
    COMPILER is None, reason="No C++ compiler available to verify the templates"
)

#: `bits/stdc++.h` is a GCC extension that Apple clang does not ship, and the
#: scaffold's `main` has to come last, so the harness supplies both itself.
PRELUDE = """#include <algorithm>
#include <array>
#include <chrono>
#include <climits>
#include <cstdint>
#include <functional>
#include <iostream>
#include <numeric>
#include <queue>
#include <random>
#include <stack>
#include <string>
#include <utility>
#include <vector>
using namespace std;
using ll = long long;
"""


def _library_source() -> str:
    """Every template except the scaffold, in declaration order."""
    bodies = [t.code for t in TEMPLATES if t.slug != "scaffold"]
    return PRELUDE + "\n\n".join(bodies) + "\n\nint main() { return 0; }\n"


def _compile(source: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "templates.cpp"
        path.write_text(source, encoding="utf-8")
        return subprocess.run(
            [COMPILER, "-std=c++17", "-fsyntax-only", "-Wall", str(path)],
            capture_output=True,
            text=True,
            timeout=180,
        )


def test_the_whole_library_compiles():
    result = _compile(_library_source())
    assert result.returncode == 0, (
        "The template library does not compile:\n" + result.stderr
    )


def test_scaffold_compiles_on_its_own():
    """The scaffold is a complete program, not a fragment."""
    result = _compile(
        TEMPLATES_BY_SLUG["scaffold"].code.replace(
            "#include <bits/stdc++.h>", PRELUDE.split("using namespace")[0]
        )
    )
    assert result.returncode == 0, result.stderr


def test_every_template_is_documented():
    """A template without pitfalls or a reason is a snippet, not a template."""
    for template in TEMPLATES:
        assert template.why, f"{template.slug} has no rationale"
        assert template.complexity, f"{template.slug} has no complexity"
        assert template.typing_minutes > 0, f"{template.slug} has no typing estimate"
        if template.slug != "scaffold":
            assert template.pitfalls, f"{template.slug} lists no pitfalls"


def test_slugs_are_unique():
    slugs = [t.slug for t in TEMPLATES]
    assert len(slugs) == len(set(slugs))


def test_detail_round_trips():
    detail = template_detail("dsu")
    assert detail is not None
    assert detail["code"].startswith("struct DSU")
    assert template_detail("no-such-template") is None
