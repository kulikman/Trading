"""Сообщения «СИСТЕМА» (SPEC §12). Telegram подключается в T18; до этого — в лог."""

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class SystemNotifier(Protocol):
    def system(self, text: str, *, code: str | None = None) -> None:
        """Сообщение «СИСТЕМА»: сбой данных, расхождение, молчание сервиса."""


class LoggingNotifier:
    def system(self, text: str, *, code: str | None = None) -> None:
        logger.warning("SYSTEM: %s", text, extra={"code": code})
