# Anti-Hallucination Rules

id: core/anti-hallucination
version: 1.0.0
applies_to: all

## Purpose

Prevent agents from inventing project facts, implementation details or completed work.

## Never invent

- APIs
- routes
- database tables or columns
- environment variables
- external integrations
- services
- package names
- generated files
- test results
- build results
- completed work

## Required behavior

Before making a claim, verify it from one of:

1. Existing repository files.
2. Installed dependencies.
3. User-provided requirements.
4. Actual command output.

If something is unclear, ask a question or mark it as an assumption.

## Before saying done

Check:

- Did I inspect the relevant files?
- Did I run the available checks?
- Did I invent any API, env var or DB field?
- Did I touch protected files?
- Did I change behavior outside the request?
- Is the result actually complete?
