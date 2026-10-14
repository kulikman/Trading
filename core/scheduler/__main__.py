"""`make run-scheduler`: планировщик с хранилищем в Postgres."""

import logging

from core.config import load_config
from core.db.session import database_url
from core.scheduler.jobs import handlers
from core.scheduler.runner import create_scheduler, register_jobs


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    handlers()  # реестр плагинов проверяется при старте: неисправный плагин — ошибка сразу
    scheduler = create_scheduler(database_url())
    register_jobs(scheduler, load_config().schedule)
    scheduler.start()


if __name__ == "__main__":  # pragma: no cover
    main()
