# Domain: Trading Options

id: domain/trading-options
version: 1.0.0

## Rules

- Do not invent strategies, broker behavior, market data fields, fills, Greeks, risk metrics, backtest results, execution costs or performance claims.
- Only use computed or source-backed metrics.
- Treat backtests as high-risk: include assumptions, time range, fees, slippage and out-of-sample separation.
- Do not optimize for more signals unless expected after-cost quality improves.
- Stop and ask before changing signal-generation logic, execution assumptions, risk management, position sizing or market-data ingestion.

## Useful skills

- code-audit
- security-review
- business-risk-review
- performance-audit
- test-generation
