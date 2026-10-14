"""`make run-calendar`: разовый прогон «Календаря» вне расписания (проверка, наполнение)."""

import logging

from agents.calendar.job import run_calendar

logger = logging.getLogger("agents.calendar")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = run_calendar()
    if result is None:
        logger.info("Сегодня неторговый день — календарь не запускался.")
        return
    logger.info(
        "Новых событий: %d, обновлено: %d, расхождений дат: %d %s, задач в плане: %d",
        len(result.created),
        len(result.updated),
        len(result.mismatches),
        result.mismatches,
        result.jobs_planned,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
