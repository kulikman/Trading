from datetime import date

import httpx
import pytest

from adapters.cboe.client import CboeClient, parse_vix_history
from adapters.errors import DataError
from core.config import load_config

SETTINGS = load_config().sources.cboe
CSV = (
    "DATE,OPEN,HIGH,LOW,CLOSE\n"
    "10/13/2026,15.61,15.61,15.17,15.27\n"
    "10/14/2026,15.17,17.45,14.98,16.87\n"
)


def test_parse_and_window() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/VIX_History.csv")
        assert request.headers["User-Agent"] == SETTINGS.user_agent
        return httpx.Response(200, text=CSV)

    client = CboeClient.create(SETTINGS, transport=httpx.MockTransport(handler))
    assert client.vix_closes(date(2026, 10, 14), date(2026, 10, 15)) == {date(2026, 10, 14): 16.87}


def test_format_change_is_data_error() -> None:
    with pytest.raises(DataError, match="unexpected header"):
        parse_vix_history("Date;Close\n")
    with pytest.raises(DataError, match="bad row"):
        parse_vix_history("DATE,OPEN,HIGH,LOW,CLOSE\n2026-10-14,1,2,3,x\n")
