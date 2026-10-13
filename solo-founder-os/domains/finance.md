# Domain: Finance

id: domain/finance
version: 1.0.0

## Rules

- Do not invent financial balances, invoices, fees, taxes, payouts, reconciliation states or accounting logic.
- Treat money movement, invoices, payments and reporting as high-risk logic.
- Be careful with rounding, currency, timezone and audit trails.
- Stop and ask before changing migrations, payment flows, invoice numbering, financial exports or reconciliation logic.
- Never expose customer financial data or payment secrets.

## Useful skills

- security-review
- database-migration
- business-risk-review
- release
