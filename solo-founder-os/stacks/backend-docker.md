# Stack: Backend + Docker

id: stack/backend-docker
version: 1.0.0

## Rules

- This is backend/API infrastructure, not a frontend repository.
- Do not apply React, Next.js or Flutter assumptions.
- Do not invent services, endpoints, ports, database tables, JWT claims, env vars or Docker service names.
- Be careful with auth, gateway routes, SSL, migrations and deployment config.
- Keep local, staging and production configs conceptually aligned when changing routes.
- Never commit secrets, generated certificates, private keys, DB dumps or password files.

## Checks

Preferred checks:

```bash
docker compose config
```

If Go services are present:

```bash
go test ./...
go vet ./...
```

If Node services are present:

```bash
npm test
npm run lint
npm run build
```

If Python services are present:

```bash
pytest
ruff check .
```

Use only commands that exist in the project.
