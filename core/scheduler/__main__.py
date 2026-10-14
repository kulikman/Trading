"""`make run-scheduler`: планировщик с хранилищем в Postgres."""

import logging

from sqlalchemy.orm import Session

from core.config import load_config
from core.db.session import database_url
from core.registry.state import sync_plugins
from core.scheduler.jobs import engine, handlers
from core.scheduler.runner import create_scheduler, register_jobs


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # httpx на INFO пишет полный адрес запроса — у FRED и Alpha Vantage в нём ключ API
    logging.getLogger("httpx").setLevel(logging.WARNING)
    handlers()  # реестр плагинов проверяется при старте: неисправный плагин — ошибка сразу
    config = load_config()
    with Session(engine()) as session, session.begin():
        sync_plugins(session, config.registry)  # enabled — из registry.yaml, стадия — из БД
    scheduler = create_scheduler(database_url())
    register_jobs(scheduler, config.schedule)
    scheduler.start()


if __name__ == "__main__":  # pragma: no cover
    main()
