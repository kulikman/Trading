from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.health import SourceHealth
from core.db import models as orm
from notify.system import (
    DbSystemNotifier,
    collect_error_messages,
    save_source_health,
    send_system_messages,
)

AT = datetime(2026, 10, 15, 11, 0, tzinfo=UTC)


class Bot:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def send(self, text: str) -> int:
        self.texts.append(text)
        return len(self.texts)


def error(
    source: str, minutes: int, *, level: str = "error", resolved: bool = False
) -> orm.ErrorLog:
    return orm.ErrorLog(
        at=AT + timedelta(minutes=minutes),
        level=level,
        source=source,
        ticker="NFLX",
        stage="T-7",
        error_type="DataError" if level == "error" else "OK",
        message="massive: HTTP 429",
        resolved_at=AT + timedelta(minutes=minutes + 1) if resolved else None,
    )


def texts(session: Session) -> list[str]:
    return [
        m.text for m in session.scalars(select(orm.SystemMessage).order_by(orm.SystemMessage.id))
    ]


def test_one_message_per_outage_and_recovery(session: Session) -> None:
    session.add_all([error("options", 0), error("options", 1), error("macro", 2)])
    session.flush()
    assert collect_error_messages(session) == 2  # второй сбой options — тот же простой
    session.add(error("options", 5, level="ok"))
    session.flush()
    assert collect_error_messages(session) == 1
    assert collect_error_messages(session) == 0  # разобранное не повторяется
    assert texts(session) == [
        "СИСТЕМА · сбой options NFLX T-7: DataError: massive: HTTP 429",
        "СИСТЕМА · сбой macro NFLX T-7: DataError: massive: HTTP 429",
        "СИСТЕМА · options: снова работает",
    ]
    bot = Bot()
    assert send_system_messages(session, bot, AT) == 3
    assert send_system_messages(session, bot, AT) == 0  # отправленное не повторяется
    assert bot.texts == texts(session)


def test_new_outage_after_recovery_is_announced(session: Session) -> None:
    session.add(error("options", 0, resolved=True))
    session.flush()
    collect_error_messages(session)
    session.add(error("options", 10))
    session.flush()
    assert collect_error_messages(session) == 1  # прошлый сбой решён — это новый


def test_source_health_keeps_latest(session: Session) -> None:
    save_source_health(session, {"finnhub": SourceHealth(last_ok_at=AT)})
    save_source_health(
        session,
        {
            "finnhub": SourceHealth(
                last_ok_at=AT - timedelta(hours=1), last_error_at=AT, last_error="HTTP 429"
            )
        },
    )
    row = session.get(orm.SourceStatus, "finnhub")
    assert row is not None
    assert (row.last_ok_at, row.last_error) == (AT, "HTTP 429")  # старая отметка не затирает новую


def test_db_notifier_writes_journal(session: Session) -> None:
    notifier = DbSystemNotifier(
        lambda: Session(bind=session.connection(), join_transaction_mode="create_savepoint"),
        clock=lambda: AT,
    )
    notifier.system("Календарь: даты расходятся", code="DATA_CALENDAR")
    row = session.scalars(select(orm.SystemMessage)).one()
    assert (row.at, row.code, row.text, row.sent_at) == (
        AT,
        "DATA_CALENDAR",
        "Календарь: даты расходятся",
        None,
    )
