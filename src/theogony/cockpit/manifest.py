"""Manifest repository — single Markdown file under ``data/cockpit/`` (PHX-0074)."""

from __future__ import annotations

import os
import socket
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from theogony.config.settings import Settings


def _default_manifest_markdown() -> str:
    host = socket.gethostname()
    return (
        f"# Manifest of {host}\n\n"
        "## Primäre Wissensdomäne\n\n"
        "(declare what knowledge this Pantheon instance is for)\n\n"
        "## Sprachen\n\n"
        "- Primär: en\n\n"
        "## Ausschlüsse\n\n"
        "(declare what this instance does NOT cover)\n\n"
        "## Aktualisierungs-Verhalten\n\n"
        "(declare how new knowledge is acquired)\n"
    )


def manifest_paths(settings: Settings) -> tuple[Path, Path]:
    mp = settings.cockpit.manifest_path
    manifest_file = mp if mp.is_absolute() else (settings.data_dir / mp).resolve()
    history_dir = manifest_file.parent / "manifest.history"
    return manifest_file, history_dir


@dataclass(frozen=True)
class ManifestHistoryEntry:
    timestamp: str


class ManifestRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._file, self._history = manifest_paths(settings)

    def read(self) -> str:
        if not self._file.exists():
            return _default_manifest_markdown()
        return self._file.read_text(encoding="utf-8")

    def list_history(self) -> list[ManifestHistoryEntry]:
        if not self._history.exists():
            return []
        names = sorted(
            (p.stem for p in self._history.iterdir() if p.is_file() and p.suffix == ".md"),
            reverse=True,
        )
        return [ManifestHistoryEntry(timestamp=t) for t in names]

    def read_snapshot(self, timestamp: str) -> str:
        path = self._history / f"{timestamp}.md"
        if not path.is_file():
            raise FileNotFoundError(str(path))
        return path.read_text(encoding="utf-8")

    def save(self, content: str) -> None:
        if self._settings.cockpit.sample_only:
            raise PermissionError("manifest save blocked in sample-only mode")
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._history.mkdir(parents=True, exist_ok=True)
        prev = self._file.read_text(encoding="utf-8") if self._file.exists() else None
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        if prev is not None:
            (self._history / f"{ts}.md").write_text(prev, encoding="utf-8")
        tmp = self._file.with_suffix(self._file.suffix + ".tmp")
        with tmp.open("wb") as fh:
            fh.write(content.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self._file)
        if self._settings.cockpit.manifest_git_commit:
            try:
                rel = (
                    str(self._file.relative_to(Path.cwd()))
                    if self._file.is_relative_to(Path.cwd())
                    else str(self._file)
                )
                subprocess.run(["git", "add", rel], check=False, capture_output=True, timeout=30)
                subprocess.run(
                    ["git", "commit", "-m", f"manifest: {socket.gethostname()} @ {ts}"],
                    check=False,
                    capture_output=True,
                    timeout=30,
                )
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
