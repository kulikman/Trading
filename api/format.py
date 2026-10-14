"""Числа и время для дашборда (DASHBOARD.md §1, §5): значение для логики + готовая строка.

Фронтенд показывает только `display` и красит по `tone` — сам ничего не форматирует и не считает.
Числа по-русски: разделитель тысяч — неразрывный пробел, дробная часть — запятая;
цены — с точкой (как в терминале брокера: «921.00»).
"""

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from core.session_guard import to_et

MSK = ZoneInfo("Europe/Moscow")
NBSP = "\u00a0"
EMPTY = "нет данных"

Tone = Literal["positive", "negative", "action", "neutral"]


class Num(BaseModel):
    """Число дашборда: value — для логики и тестов, display — для показа, tone — цвет."""

    value: float | None
    display: str
    tone: Tone = "neutral"


def empty(text: str = EMPTY) -> Num:
    return Num(value=None, display=text)


def money(value: float | None, *, signed: bool = False) -> Num:
    """$103 450 / +$412 / −$90; signed — со знаком и цветом."""
    if value is None:
        return empty()
    body = f"${_grouped(abs(value), 0)}"
    return Num(value=value, display=_sign(value, signed) + body, tone=_tone(value, signed))


def percent(value: float | None, *, signed: bool = False, digits: int = 1) -> Num:
    """Доля → «+4,8%». value — доля (0.048), как в расчётах."""
    if value is None:
        return empty()
    body = _grouped(abs(value) * 100, digits) + "%"
    return Num(value=value, display=_sign(value, signed) + body, tone=_tone(value, signed))


def ratio(value: float | None, digits: int = 2) -> Num:
    """Безразмерное число (Sharpe, profit factor): «1,24»."""
    if value is None:
        return empty()
    sign = "−" if value < 0 else ""
    return Num(value=value, display=sign + _grouped(abs(value), digits))


def count(value: int) -> Num:
    return Num(value=value, display=_grouped(value, 0))


def price(value: float | None) -> Num:
    """Цена инструмента: «921.00»."""
    if value is None:
        return empty()
    return Num(value=value, display=f"{value:.2f}")


def et_msk(moment: datetime) -> str:
    """«09:30 ET / 16:30 МСК»; наивное время — ошибка."""
    et = to_et(moment)
    return f"{et:%H:%M} ET / {et.astimezone(MSK):%H:%M} МСК"


def day(value: date) -> str:
    return f"{value:%d.%m.%Y}"


def day_et(moment: datetime) -> date:
    return to_et(moment).date()


def _grouped(value: float, digits: int) -> str:
    text = f"{value:,.{digits}f}"
    return text.replace(",", NBSP).replace(".", ",")


def _sign(value: float, signed: bool) -> str:
    if value < 0:
        return "−"
    return "+" if signed and value > 0 else ""


def _tone(value: float, signed: bool) -> Tone:
    if not signed or value == 0:
        return "neutral"
    return "positive" if value > 0 else "negative"
