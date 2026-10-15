"""FastAPI дашборда (T19a, DASHBOARD.md §5, §7): только чтение, доступ только по токену.

Токен — DASHBOARD_API_TOKEN, заголовок `Authorization: Bearer <токен>`. Сайт (`web/`) ходит сюда
только с сервера; браузер API не видит. Paper и Real не смешиваются: режим — параметр запроса,
и каждый ответ считается только по сделкам этого режима.
"""

import secrets
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from adapters.api_model import require_env
from adapters.broker.factory import create_cost_model
from api import account, companies, events, system, trades
from api.trades_data import closed_trades, first_card_at, open_cards
from core.config import load_config
from core.config.thresholds import Thresholds
from core.db.session import create_db_engine
from execution.cash import real_capital
from execution.costs import CostModel
from learning.costs import compare_costs, real_executions

TOKEN_ENV = "DASHBOARD_API_TOKEN"  # noqa: S105 — имя переменной окружения, не секрет
CHANGES_DEFAULT_DAYS = 7

Mode = Literal["paper", "real"]
Clock = Callable[[], datetime]


def create_app(
    *,
    engine: Engine | Connection | None = None,
    token: str | None = None,
    clock: Clock = lambda: datetime.now(UTC),
    thresholds: Thresholds | None = None,
    cost_model: CostModel | None = None,
) -> FastAPI:
    """Приложение; без токена в окружении не стартует (открытый API с балансом недопустим)."""
    expected = token if token is not None else require_env(TOKEN_ENV)
    db = engine if engine is not None else create_db_engine()
    limits = thresholds if thresholds is not None else load_config().thresholds
    costs_model = cost_model if cost_model is not None else create_cost_model(load_config().broker)

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        scheme, _, given = (authorization or "").partition(" ")
        if scheme != "Bearer" or not given or not secrets.compare_digest(given, expected):
            raise HTTPException(status_code=401, detail="unauthorized")

    def session() -> Iterator[Session]:
        with Session(db) as s:
            yield s

    app = FastAPI(title="Earnings Engine dashboard API", dependencies=[Depends(authorize)])
    Db = Annotated[Session, Depends(session)]

    def capital(mode: Mode, db: Session) -> float | None:
        # Paper — капитал из thresholds.yaml; Real — пополнения и выводы (нет — счёт не подключён).
        return limits.capital.module_usd if mode == "paper" else real_capital(db)

    @app.get("/api/status")
    def status(db: Db) -> system.Status:
        return system.status_view(db, clock(), limits)

    @app.get("/api/account")
    def account_bar(db: Db, mode: Mode = "paper") -> account.AccountBar:
        is_paper = mode == "paper"
        return account.account_bar(
            mode,
            closed_trades(db, paper=is_paper),
            open_cards(db, paper=is_paper),
            capital=capital(mode, db),
            thresholds=limits,
            now=clock(),
        )

    @app.get("/api/account/summary")
    def account_summary(db: Db, mode: Mode = "paper") -> account.AccountSummary:
        is_paper = mode == "paper"
        return account.account_summary(
            mode,
            closed_trades(db, paper=is_paper),
            capital=capital(mode, db),
            thresholds=limits,
            now=clock(),
            first_card_at=first_card_at(db, paper=is_paper),
        )

    @app.get("/api/changes")
    def changes(db: Db, since: datetime | None = None) -> events.Changes:
        moment = since or clock() - timedelta(days=CHANGES_DEFAULT_DAYS)
        if moment.tzinfo is None:
            raise HTTPException(status_code=422, detail="since must include a timezone")
        return events.changes_view(db, moment)

    @app.get("/api/today")
    def today(db: Db) -> events.Today:
        return events.today_view(db, clock(), open_cards(db, paper=True))

    @app.get("/api/week")
    def week(db: Db) -> events.Week:
        return events.week_view(db, clock(), limits)

    @app.get("/api/week/terminal")
    def terminal(db: Db) -> events.Terminal:
        return events.terminal_view(db, clock())

    @app.get("/api/trades")
    def trade_list(
        db: Db, state: Literal["open", "closed"] = "open", mode: Mode = "paper"
    ) -> trades.Trades:
        is_paper = mode == "paper"
        return trades.trades_view(
            state,
            open_cards(db, paper=is_paper),
            closed_trades(db, paper=is_paper),
            capital(mode, db) or limits.capital.module_usd,
            compare_costs(
                real_executions(db),
                costs_model,
                alert=limits.costs.paper_vs_real_alert,
                min_fills=limits.costs.min_real_fills,
            ),
            limits.dashboard.cost_divergence,
        )

    @app.get("/api/trades/{card_id}")
    def trade_card(db: Db, card_id: int) -> trades.Card:
        card = trades.card_view(db, card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="card not found")
        return card

    @app.get("/api/journal")
    def journal(
        db: Db, filter: Annotated[Literal["all", "entered", "skipped"], Query()] = "all"
    ) -> events.Journal:
        return events.journal_view(db, clock(), filter)

    @app.get("/api/sectors")
    def sectors(db: Db) -> list[companies.SectorRow]:
        return companies.sectors_view(db, clock())

    @app.get("/api/sectors/{sector_id}")
    def sector(db: Db, sector_id: str) -> companies.SectorDetail:
        detail = companies.sector_view(db, sector_id, clock())
        if detail is None:
            raise HTTPException(status_code=404, detail="sector not found")
        return detail

    @app.get("/api/companies/{ticker}/{tab}")
    def company(
        db: Db,
        ticker: str,
        tab: Literal["overview", "news", "reports", "financials", "track"],
    ) -> (
        companies.Overview
        | companies.News
        | companies.Reports
        | companies.Financials
        | companies.Track
    ):
        view = companies.company_tab(db, ticker.upper(), tab, clock())
        if view is None:
            raise HTTPException(status_code=404, detail="company not found")
        return view

    @app.get("/api/system/models")
    def models(db: Db) -> system.Models:
        return system.models_view(db)

    @app.get("/api/system/errors")
    def errors(db: Db, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> system.Errors:
        return system.errors_view(db, limit)

    @app.get("/api/system/heartbeat")
    def heartbeat(db: Db, watchdog: bool = False) -> system.Heartbeat:
        return system.heartbeat_view(db, clock(), limits, watchdog=watchdog)

    @app.get("/api/system/plugins")
    def plugins(db: Db) -> list[system.PluginRow]:
        return system.plugins_view(db)

    return app
