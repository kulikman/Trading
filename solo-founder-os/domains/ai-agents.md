# Domain: AI Agents

id: domain/ai-agents
version: 1.0.0

## Rules

- Do not invent agent capabilities, tool permissions, memory behavior, model behavior or integration status.
- Treat tools, MCP servers, prompts, rules and generated instructions as executable system surface.
- Be careful with prompt injection, untrusted imported skills and command execution.
- Keep agent rules concise and stack-specific to avoid context bloat and conflicting instructions.
- Stop and ask before adding external skills, shell commands, repo-wide sync behavior or auto-update logic.

## Useful skills

- code-audit
- security-review
- test-generation
- product-review
