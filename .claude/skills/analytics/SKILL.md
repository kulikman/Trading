# Skill: /analytics

## Trigger
`/analytics [tracking, events, funnel, PostHog, GA4, metrics request]`

## Purpose
Define practical product analytics so a solo founder can see activation,
conversion, retention, and failure points without drowning in dashboards.

## Use when

- adding PostHog, GA4, or custom tracking
- choosing events to log
- designing activation funnels
- defining retention or conversion metrics
- reviewing whether analytics are trustworthy

## Process

1. Identify the core product journey.
2. Define the few events that prove movement through that journey.
3. Separate product metrics from vanity metrics.
4. Specify event names and properties.
5. Check privacy and consent implications.

## Output

```
## Analytics Plan: [flow]

### North Star
- metric

### Funnel
- step

### Events
- event_name: properties

### Dashboards
- chart or view

### Privacy
- data to avoid or minimize

### Verification
- how to confirm events fire
```

## Guardrails

- never track secrets, tokens, payment data, or sensitive PII
- do not invent analytics providers that are not installed
- prefer fewer high-signal events over noisy tracking
- keep event names stable and documented
