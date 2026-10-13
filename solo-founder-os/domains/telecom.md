# Domain: Telecom

id: domain/telecom
version: 1.0.0

## Rules

- Do not invent telecom provider APIs, tariff logic, coverage claims, roaming behavior, eSIM activation flows or IMSI behavior.
- Treat pricing, coverage, supplier contracts and availability as source-backed data only.
- Be careful with payment, order, activation, customer identity and support flows.
- Do not expose provider credentials, ICCID, IMSI, customer PII or activation secrets.

## Useful skills

- code-audit
- release
- security-review
- ui-review
- database-migration
