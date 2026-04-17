"""Tests for theogony.config.logging."""

from __future__ import annotations

import logging

import pytest
from rich.logging import RichHandler

from theogony.config.logging import (
    THEOGONY_LOGGER_NAME,
    get_logger,
    setup_logging,
)
from theogony.config.settings import Settings


@pytest.fixture(autouse=True)
def _reset_theogony_logger() -> None:
    """Tear down the Theogony logger between tests so each one starts clean."""
    logger = logging.getLogger(THEOGONY_LOGGER_NAME)
    handlers = list(logger.handlers)
    yield
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    for h in handlers:
        logger.addHandler(h)
    logger.setLevel(logging.WARNING)
    logger.propagate = True


class TestSetupLogging:
    def test_installs_rich_handler(self) -> None:
        logger = setup_logging()
        assert any(isinstance(h, RichHandler) for h in logger.handlers)

    def test_returns_theogony_logger(self) -> None:
        logger = setup_logging()
        assert logger.name == THEOGONY_LOGGER_NAME

    def test_default_level_is_info(self) -> None:
        logger = setup_logging()
        assert logger.level == logging.INFO

    def test_respects_settings_log_level(self) -> None:
        settings = Settings(log_level="DEBUG")
        logger = setup_logging(settings)
        assert logger.level == logging.DEBUG

    def test_invalid_log_level_falls_back_to_info(self) -> None:
        settings = Settings(log_level="NONSENSE")
        logger = setup_logging(settings)
        assert logger.level == logging.INFO

    def test_idempotent_does_not_duplicate_handlers(self) -> None:
        first = setup_logging()
        first_count = sum(isinstance(h, RichHandler) for h in first.handlers)
        second = setup_logging()
        second_count = sum(isinstance(h, RichHandler) for h in second.handlers)
        assert first_count == 1
        assert second_count == 1

    def test_force_replaces_existing_rich_handler(self) -> None:
        original = setup_logging()
        original_handler = next(h for h in original.handlers if isinstance(h, RichHandler))
        replaced = setup_logging(force=True)
        new_handler = next(h for h in replaced.handlers if isinstance(h, RichHandler))
        assert new_handler is not original_handler

    def test_idempotent_call_updates_level(self) -> None:
        setup_logging(Settings(log_level="WARNING"))
        logger = setup_logging(Settings(log_level="ERROR"))
        assert logger.level == logging.ERROR

    def test_does_not_propagate_to_root(self) -> None:
        logger = setup_logging()
        assert logger.propagate is False


class TestGetLogger:
    def test_root_returns_theogony_logger(self) -> None:
        assert get_logger().name == THEOGONY_LOGGER_NAME

    def test_explicit_root_name_returns_theogony_logger(self) -> None:
        assert get_logger(THEOGONY_LOGGER_NAME).name == THEOGONY_LOGGER_NAME

    def test_short_name_is_namespaced_under_theogony(self) -> None:
        assert get_logger("extraction").name == f"{THEOGONY_LOGGER_NAME}.extraction"

    def test_already_namespaced_name_is_returned_verbatim(self) -> None:
        full = f"{THEOGONY_LOGGER_NAME}.api.routes.query"
        assert get_logger(full).name == full

    def test_module_dunder_name_pattern(self) -> None:
        """`get_logger(__name__)` is the idiomatic call site."""
        log = get_logger("theogony.extraction.pipeline")
        assert log.name == "theogony.extraction.pipeline"

    def test_child_logger_propagates_to_parent_handler(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        setup_logging(Settings(log_level="INFO"), force=True)
        child = get_logger("retrieval.multi_hop")
        child.info("constellation_assembled nodes=37")
        captured = capsys.readouterr()
        emitted = captured.out + captured.err
        assert "constellation_assembled" in emitted
