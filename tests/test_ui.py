from __future__ import annotations

from pathlib import Path

from app import ui


def test_logging_is_rotating_and_keeps_messages_path_free(tmp_path: Path) -> None:
    logger = ui.configure_logging(tmp_path)
    logger.info("read-only scan completed")
    handler = logger.handlers[0]
    assert handler.maxBytes == 256 * 1024
    assert handler.backupCount == 3
    assert (tmp_path / "Logs" / "ui.log").exists()


def test_ui_copy_explains_unsigned_and_confirmation_boundaries() -> None:
    source = Path(ui.__file__).read_text(encoding="utf-8")
    assert "Unofficial, unsigned build" in source
    assert "does not change device drivers" in source
    assert "pre-restore backup" in source
    assert "Proposed mutations" in source
    assert "Confirm repair" in source
