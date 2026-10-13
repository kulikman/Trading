# Security Rules

id: core/security
version: 1.0.0
applies_to: all

## Purpose

Protect secrets, credentials, private data and production systems during AI-assisted development.

## Never commit

- `.env*`
- API keys
- tokens
- private keys
- generated certificates
- password files
- DB dumps
- production data
- raw customer data
- logs with secrets or personal data
- screenshots containing credentials

## Before editing sensitive areas

Stop and ask before changing:

- auth logic
- payment flows
- migrations
- RLS policies
- deployment scripts
- production config
- secrets management
- generated database types

## Security review checklist

- Are secrets excluded from git?
- Are env variables documented without values?
- Are auth and role checks preserved?
- Are server-only functions kept server-side?
- Are user inputs validated?
- Are errors safe and non-leaky?
