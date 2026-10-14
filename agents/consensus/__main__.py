"""`make run-consensus`: разовый снимок консенсуса вне расписания."""

import logging

from agents.consensus.job import run_consensus_snapshot

logger = logging.getLogger("agents.consensus")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    rows = run_consensus_snapshot()
    if rows is None:
        logger.info("Сегодня неторговый день — снимок не делался.")
        return
    logger.info("Строк консенсуса сохранено: %d", rows)


if __name__ == "__main__":  # pragma: no cover
    main()
