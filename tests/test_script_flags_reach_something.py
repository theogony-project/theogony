"""Every `--flag` a script declares must be read somewhere in that script.

`scripts/mesh_corpus_answers.py` declared `--seeds` and never passed it on. Two
measurements were reported as "k_seeds=1" that ran at the library default, and
nothing anywhere said otherwise: argparse accepts the flag, the script runs, the
output looks right. **From the outside a flag that reaches nothing is
indistinguishable from one that works** — which is what makes this class of bug
expensive in a repository whose product is measurements.

This is a static check on purpose. Running each script to find out is not
possible (they want a mesh, an embedder and an API key), and the property worth
holding is syntactic anyway: the parsed attribute has to be *mentioned*.

What it cannot catch: a flag that is read and then used wrongly. It catches the
one that is not read at all, which is the one that leaves no trace (PHX-1097).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SCRIPTS = sorted((Path(__file__).resolve().parents[1] / "scripts").glob("*.py"))


def _declared_and_used(tree: ast.AST) -> tuple[list[str], set[str]]:
    declared: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and node.args
        ):
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and str(first.value).startswith("--")):
                continue
            explicit = next(
                (
                    kw.value.value
                    for kw in node.keywords
                    if kw.arg == "dest" and isinstance(kw.value, ast.Constant)
                ),
                None,
            )
            declared.append(str(explicit or str(first.value)[2:].replace("-", "_")))
    used = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    return declared, used


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_every_declared_flag_is_read(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    declared, used = _declared_and_used(tree)
    dead = [name for name in declared if name not in used]
    assert not dead, f"{path.name} declares {dead} and never reads it"
