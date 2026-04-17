"""
Rich-based logging setup.

Theogony's runtime emits a lot of structured chatter — pipeline stage
transitions, retrieval breakdowns, Oneiros tick summaries, LLM
audit-call decisions. The default Python logging handler renders these
poorly; rich's RichHandler turns them into readable, colour-coded,
file:line-anchored output without any structured-logging framework.

Discipline (Plan §3.6, talos.md §7):

- Secrets are protected at the Settings layer (SecretStr). This module
  never touches secrets directly. It MUST NOT log a `Settings` instance
  whole, and MUST NOT format-log api-key values; the SecretStr wrapper
  already mangles repr, which is the second line of defence.
- INFO is the default; DEBUG is opt-in via `THEOGONY_LOG_LEVEL=DEBUG`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rich.logging import RichHandler

if TYPE_CHECKING:
    from theogony.config.settings import Settings

THEOGONY_LOGGER_NAME = "theogony"

_DEFAULT_FORMAT = "%(message)s"
_DEFAULT_DATE_FORMAT = "[%X]"


def setup_logging(settings: Settings | None = None, *, force: bool = False) -> logging.Logger:
    """Install a Rich handler on the ``theogony`` logger.

    Idempotent by default: if a Theogony Rich handler is already
    installed, this is a no-op (so re-running ``theogony serve`` or
    importing pipelines twice does not duplicate output). Pass
    ``force=True`` to tear down and reinstall — primarily a hook for
    tests that need to assert on a fresh handler.

    Args:
        settings: optional :class:`~theogony.config.settings.Settings`.
            When omitted, uses ``logging.INFO`` and reads no env vars.
            The deferred import keeps this module importable even
            before ``pydantic-settings`` is wired into a deployment.
        force: if True, remove any existing Theogony Rich handler
            before installing a fresh one.

    Returns:
        The configured ``theogony`` logger. Submodule loggers obtained
        via ``logging.getLogger("theogony.api")``, ``"theogony.extraction"``,
        etc., propagate up to this handler.
    """
    level_name = (settings.log_level if settings is not None else "INFO").upper()
    level = logging.getLevelNamesMapping().get(level_name, logging.INFO)

    logger = logging.getLogger(THEOGONY_LOGGER_NAME)

    existing_rich = [
        h for h in logger.handlers if isinstance(h, RichHandler)
    ]
    if existing_rich and not force:
        logger.setLevel(level)
        return logger

    if force:
        for handler in existing_rich:
            logger.removeHandler(handler)

    handler = RichHandler(
        level=level,
        rich_tracebacks=True,
        show_time=True,
        show_level=True,
        show_path=True,
        markup=False,
    )
    handler.setFormatter(logging.Formatter(fmt=_DEFAULT_FORMAT, datefmt=_DEFAULT_DATE_FORMAT))

    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child of the ``theogony`` logger.

    Use as ``log = get_logger(__name__)`` inside Theogony modules. If
    ``name`` already starts with ``theogony``, it is returned verbatim;
    otherwise it is dot-joined to the root.
    """
    if name is None or name == THEOGONY_LOGGER_NAME:
        return logging.getLogger(THEOGONY_LOGGER_NAME)
    if name.startswith(f"{THEOGONY_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{THEOGONY_LOGGER_NAME}.{name}")
