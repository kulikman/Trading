from datetime import UTC, date, datetime

import pytest

from adapters.edgar.client import EdgarClient, sec_user_agent
from adapters.edgar.financials import financial_quarters, merge_candidates, quarterly_values
from adapters.edgar.models import CompanyFacts, XbrlFact
from adapters.errors import DataError
from core.config import ConfigError, load_config
from core.config.sources import EdgarSettings
from tests.adapters.fakes import Body, FakeApi, load_json

UA = "TradingEarningsEngine test@example.com"
GS = 886982


@pytest.fixture
def settings() -> EdgarSettings:
    return load_config().sources.edgar


def client(settings: EdgarSettings, fake: FakeApi) -> EdgarClient:
    return EdgarClient.create(settings, UA, transport=fake.transport())


def routes() -> FakeApi:
    return FakeApi(
        {
            "/submissions/CIK0000886982.json": lambda _: load_json("edgar", "submissions_gs.json"),
            "/api/xbrl/companyfacts/CIK0000886982.json": lambda _: load_json(
                "edgar", "companyfacts_gs.json"
            ),
            "/files/company_tickers.json": lambda _: load_json("edgar", "company_tickers.json"),
        }
    )


def test_filings_recorded_filters_forms_and_sends_user_agent(settings: EdgarSettings) -> None:
    fake = routes()
    filings = client(settings, fake).filings(GS)
    assert {f.form for f in filings} == {"8-K", "10-Q"}  # 424B2 отфильтрованы
    latest = filings[0]
    assert (latest.form, latest.filing_date, latest.items) == (
        "8-K",
        date(2026, 10, 13),
        ["2.02", "7.01", "9.01"],
    )
    assert latest.accepted_at == datetime(2026, 10, 13, 11, 32, 56, tzinfo=UTC)
    assert latest.url(settings.archives_base_url) == (
        "https://www.sec.gov/Archives/edgar/data/886982/000088698226000529/gs-20261013.htm"
    )
    assert fake.requests[0].headers["User-Agent"] == UA


def test_earnings_releases_are_8k_item_2_02(settings: EdgarSettings) -> None:
    releases = client(settings, routes()).earnings_releases(GS)
    assert [f.filing_date for f in releases] == [
        date(2026, 10, 13),
        date(2026, 7, 14),
        date(2026, 4, 13),
    ]
    since = client(settings, routes()).earnings_releases(GS, since=date(2026, 7, 1))
    assert len(since) == 2


def test_ticker_ciks(settings: EdgarSettings) -> None:
    fake = routes()
    assert client(settings, fake).ticker_ciks() == {"GS": 886982, "JPM": 19617, "NVDA": 1045810}
    assert str(fake.requests[0].url) == settings.tickers_url


@pytest.mark.parametrize(
    ("path", "body", "message"),
    [
        ("/submissions/CIK0000886982.json", {"filings": {}}, "no filings.recent"),
        (
            "/submissions/CIK0000886982.json",
            {"filings": {"recent": {"form": ["8-K"], "accessionNumber": []}}},
            "missing column",
        ),
        (
            "/submissions/CIK0000886982.json",
            {
                "filings": {
                    "recent": {
                        "form": ["8-K"],
                        "accessionNumber": ["a", "b"],
                        "filingDate": ["2026-01-01"],
                        "reportDate": [""],
                        "acceptanceDateTime": [""],
                        "primaryDocument": ["x"],
                        "items": [""],
                    }
                }
            },
            "differ in length",
        ),
        (
            "/submissions/CIK0000886982.json",
            {
                "filings": {
                    "recent": {
                        "form": ["8-K"],
                        "accessionNumber": ["a"],
                        "filingDate": ["oops"],
                        "reportDate": [""],
                        "acceptanceDateTime": [""],
                        "primaryDocument": ["x"],
                        "items": [""],
                    }
                }
            },
            "unexpected filing row 0",
        ),
        ("/api/xbrl/companyfacts/CIK0000886982.json", {"cik": 1}, "unexpected companyfacts shape"),
        ("/files/company_tickers.json", {"0": {"ticker": "GS"}}, "unexpected company_tickers row"),
    ],
)
def test_bad_payloads_are_data_errors(
    settings: EdgarSettings, path: str, body: Body, message: str
) -> None:
    edgar = client(settings, FakeApi({path: lambda _: body}))
    call = {
        "/submissions/CIK0000886982.json": lambda: edgar.filings(GS),
        "/api/xbrl/companyfacts/CIK0000886982.json": lambda: edgar.company_facts(GS),
        "/files/company_tickers.json": edgar.ticker_ciks,
    }[path]
    with pytest.raises(DataError, match=message):
        call()


# --- квартальные финансы на записанных данных GS ---


def gs_facts(settings: EdgarSettings) -> CompanyFacts:
    return client(settings, routes()).company_facts(GS)


def fact_value(facts: CompanyFacts, concept: str, start: str, end: str) -> float:
    found = facts.concept(concept)
    assert found is not None
    _, values = found
    matches = [
        f
        for f in values
        if f.start == date.fromisoformat(start) and f.end == date.fromisoformat(end)
    ]
    return max(matches, key=lambda f: f.filed).val


def test_gs_quarters_direct_and_derived(settings: EdgarSettings) -> None:
    facts = gs_facts(settings)
    rows = financial_quarters("GS", facts, settings.financials)
    net_income = {r.period_end: r for r in rows if r.metric == "net_income"}
    q2 = net_income[date(2026, 6, 30)]
    assert (q2.value, q2.derived, q2.period_start) == (6_628_000_000, False, date(2026, 4, 1))
    q4 = net_income[date(2025, 12, 31)]  # отдельного Q4 нет — год минус 9 месяцев
    expected_q4 = fact_value(facts, "NetIncomeLoss", "2025-01-01", "2025-12-31") - fact_value(
        facts, "NetIncomeLoss", "2025-01-01", "2025-09-30"
    )
    assert (q4.value, q4.derived, q4.period_start, q4.form) == (
        expected_q4,
        True,
        date(2025, 10, 1),
        "10-K",
    )
    assert len(net_income) == settings.financials.quarters


def test_gs_revenue_uses_bank_tag_and_eps_is_not_derived(settings: EdgarSettings) -> None:
    rows = financial_quarters("GS", gs_facts(settings), settings.financials)
    revenue = [r for r in rows if r.metric == "revenue"]
    assert revenue
    assert {r.concept for r in revenue} == {"RevenuesNetOfInterestExpense"}
    eps = {r.period_end: r for r in rows if r.metric == "eps_diluted"}
    assert date(2025, 12, 31) not in eps  # EPS неаддитивен: Q4 не выводится разницей
    assert all(not r.derived for r in eps.values())
    assert {r.unit for r in eps.values()} == {"USD/shares"}
    cash = [r for r in rows if r.metric == "operating_cash_flow"]
    assert any(r.derived for r in cash)  # денежный поток — нарастающим итогом
    assert not [
        r for r in rows if r.metric in ("operating_income", "gross_profit")
    ]  # тегов у GS нет


def fact(start: str | None, end: str, val: float, filed: str = "2026-01-01") -> XbrlFact:
    return XbrlFact.model_validate(
        {"start": start, "end": end, "val": val, "accn": "a", "form": "10-Q", "filed": filed}
    )


def test_restatement_latest_filing_wins() -> None:
    values = quarterly_values(
        [
            fact("2026-01-01", "2026-03-31", 10, "2026-05-01"),
            fact("2026-01-01", "2026-03-31", 12, "2027-05-01"),
            fact(None, "2026-03-31", 99),
        ],  # мгновенный факт без начала периода пропускается
        concept="X",
        unit="USD",
        additive=True,
        min_days=80,
        max_days=100,
    )
    assert values[date(2026, 3, 31)].value == 12


def test_merge_candidates_earlier_tag_wins_and_later_fills_gaps() -> None:
    old = quarterly_values(
        [fact("2025-01-01", "2025-03-31", 1), fact("2025-04-01", "2025-06-30", 2)],
        concept="Old",
        unit="USD",
        additive=True,
        min_days=80,
        max_days=100,
    )
    new = quarterly_values(
        [fact("2025-04-01", "2025-06-30", 20), fact("2025-07-01", "2025-09-30", 30)],
        concept="New",
        unit="USD",
        additive=True,
        min_days=80,
        max_days=100,
    )
    merged = merge_candidates([new, old])
    assert {end.month: (v.value, v.concept) for end, v in merged.items()} == {
        3: (1, "Old"),
        6: (20, "New"),
        9: (30, "New"),
    }


def test_concept_absent_or_without_money_unit() -> None:
    facts = CompanyFacts.model_validate(
        {"cik": 1, "entityName": "X", "facts": {"us-gaap": {"Shares": {"units": {"shares": []}}}}}
    )
    assert facts.concept("Missing") is None
    assert facts.concept("Shares") is None


def test_user_agent_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", UA)
    assert sec_user_agent() == UA
    monkeypatch.delenv("SEC_USER_AGENT")
    with pytest.raises(ConfigError, match="SEC_USER_AGENT"):
        sec_user_agent()


def test_older_filing_after_newer_does_not_override() -> None:
    values = quarterly_values(
        [
            fact("2026-01-01", "2026-03-31", 12, "2027-05-01"),
            fact("2026-01-01", "2026-03-31", 10, "2026-05-01"),
        ],
        concept="X",
        unit="USD",
        additive=True,
        min_days=80,
        max_days=100,
    )
    assert values[date(2026, 3, 31)].value == 12


def test_items_may_already_be_a_list() -> None:
    from adapters.edgar.models import Filing

    filing = Filing.model_validate(
        {
            "cik": 1,
            "form": "8-K",
            "accession_number": "0001-26-000001",
            "filing_date": "2026-10-13",
            "primary_document": "x.htm",
            "items": ["2.02"],
        }
    )
    assert filing.items == ["2.02"]


BAC = 70858


def bac_routes() -> FakeApi:
    return FakeApi(
        {
            "/submissions/CIK0000070858.json": lambda _: load_json("edgar", "submissions_bac.json"),
            "/submissions/CIK0000070858-submissions-002.json": lambda _: load_json(
                "edgar", "CIK0000070858-submissions-002.json"
            ),
        }
    )


def test_since_reads_only_older_pages_covering_the_period(settings: EdgarSettings) -> None:
    fake = bac_routes()
    releases = client(settings, fake).earnings_releases(BAC, since=date(2025, 6, 1))
    assert [f.filing_date for f in releases] == [date(2026, 10, 14), date(2025, 7, 16)]
    # страница 003 (до 27.05.2025) не нужна для периода с 01.06.2025
    assert [r.url.path for r in fake.requests] == [
        "/submissions/CIK0000070858.json",
        "/submissions/CIK0000070858-submissions-002.json",
    ]


def test_without_since_only_recent_block_is_read(settings: EdgarSettings) -> None:
    fake = bac_routes()
    assert [f.form for f in client(settings, fake).filings(BAC, {"8-K"})] == ["8-K"]
    assert len(fake.requests) == 1


@pytest.mark.parametrize("files", ["oops", [{"name": "x.json"}]])
def test_bad_files_list_is_data_error(settings: EdgarSettings, files: object) -> None:
    body = load_json("edgar", "submissions_bac.json")
    body["filings"]["files"] = files
    fake = FakeApi({"/submissions/CIK0000070858.json": lambda _: body})
    with pytest.raises(DataError, match=r"filings\.files"):
        client(settings, fake).filings(BAC, since=date(2025, 1, 1))
