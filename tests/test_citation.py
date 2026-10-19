"""The citation file says what the package says.

`CITATION.cff` is what GitHub renders under "Cite this repository" and what a
citation tool or a corpus builder reads; `.zenodo.json` is what Zenodo reads
when it archives a release and mints a DOI. A version in either that disagrees
with `theogony.__version__`, or a licence that disagrees with the package
metadata, is a citation that points at the wrong thing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from theogony import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_the_citation_file_matches_the_package() -> None:
    cff = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert cff["cff-version"] == "1.2.0"
    assert cff["type"] == "software"
    assert cff["version"] == __version__, "bump CITATION.cff with __version__ (docs/RELEASING.md)"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(cff["date-released"]))
    assert cff["license"] == "Apache-2.0"
    assert cff["repository-code"] == "https://github.com/theogony-project/theogony"
    assert cff["authors"][0]["family-names"] == "Reinehr"
    assert "docs/etappes/" in cff["message"], "the figures are cited by their etappe"
    assert "3.6 points" in cff["abstract"]


def test_the_zenodo_metadata_agrees_with_the_citation_file() -> None:
    cff = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    zenodo = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert zenodo["title"] == cff["title"]
    assert zenodo["license"] == cff["license"]
    assert zenodo["upload_type"] == "software" and zenodo["access_right"] == "open"
    assert zenodo["creators"] == [{"name": "Reinehr, Jakob"}]
    assert set(zenodo["keywords"]) == set(cff["keywords"])


def test_the_package_metadata_carries_the_same_licence() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "Apache-2.0"' in pyproject
    assert '"CITATION.cff",' in pyproject, "the sdist ships the citation file"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "CITATION.cff" in readme
