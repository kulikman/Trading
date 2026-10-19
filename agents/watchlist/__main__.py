"""`make run-watchlist`: разовый запуск watchlist-refresh вне расписания (проверка, тест)."""

import logging

from agents.watchlist.job import run_watchlist_refresh

logger = logging.getLogger("agents.watchlist")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    active = run_watchlist_refresh()
    if not active:
        logger.info("Активных тикеров watchlist на этой неделе не найдено.")
        return
    logger.info("Активных тикеров: %d — %s", len(active), active)


if __name__ == "__main__":  # pragma: no cover
    main()
