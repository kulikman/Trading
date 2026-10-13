# Skill: /payments

## Trigger
`/payments [Stripe, checkout, subscription, billing, webhook, portal task]`

## Purpose
Design and review payment flows with extra caution around money, state,
webhooks, and idempotency.

## Use when

- adding Stripe checkout
- creating subscription plans
- changing billing states
- handling Stripe webhooks
- configuring customer portal flows
- testing payment lifecycle scenarios

## Process

1. Read `CLAUDE.md`
2. Read `.claude/rules/security.md`
3. Inspect existing Stripe, webhook, and subscription code before proposing changes
4. Define source of truth for payment state
5. Verify webhook signature and idempotency behavior

## Output

```
## Payments Task: [flow]

### Source Of Truth
- where state comes from

### Flow
- checkout
- webhook
- database update
- user-visible state

### Files
- path

### Tests
- lifecycle cases

### Risks
- money/state edge case
```

## Guardrails

- never trust client payloads for payment status
- never skip Stripe webhook signature verification
- never update subscription state without considering idempotency
- ask before changing billing behavior or payment webhooks
