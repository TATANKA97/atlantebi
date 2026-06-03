# Atlante BI

Atlante BI is an AI-powered BI platform for Italian SMBs. This repository starts with the product foundation only: application metadata, strict shared contracts, a technical web shell, and a query-engine boundary.

This foundation intentionally does not include AI orchestration, dashboard UI, chart rendering, query execution, introspection, or customer data storage.

## Architecture

```txt
apps/web                 Next.js App Router BFF and technical shell
packages/contracts       Shared Zod and TypeScript API contracts
packages/db              Supabase/Postgres migrations and schema checks
services/query-engine    FastAPI service boundary and driver interfaces
supabase                 Supabase CLI project and migrations
```

## Non-negotiable data rule

Supabase stores application metadata only:

- tenants and memberships
- connection metadata with `secret_ref`
- semantic layer metadata
- dashboards and widgets
- query history metadata
- audit logs

Customer database passwords, connection strings, and raw customer result rows are not stored in Supabase.

## Local checks

```bash
pnpm install
pnpm lint
pnpm typecheck
pnpm test
pnpm build

cd services/query-engine
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
```

Docker is exercised in CI with `services/query-engine/Dockerfile`.

## Connection Testing

The query-engine exposes `POST /connections/test` for SQL Server and MySQL connection checks. It resolves only password material from GCP Secret Manager; Supabase keeps connection metadata and `secret_ref`.

Secret Manager payload:

```json
{
  "password": "customer database password"
}
```

The database username is application metadata in Supabase. Passwords, DSNs, and full connection strings are not.

## Web environment

The web app uses Supabase SSR Auth with cookie-based sessions.

```bash
NEXT_PUBLIC_SUPABASE_URL=https://zzvfjqnfhuvapuvhpxee.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<supabase publishable key>
```

Use a Supabase publishable key for the browser/BFF auth flow. Do not put
`service_role`, database passwords, or customer database credentials in web
environment variables.

## Services

- Web health: `GET /api/health`
- Web auth: `/login`
- Tenant setup: `/setup`
- Query engine health: `GET /health`
- Query engine connection test: `POST /connections/test`
- Query engine run boundary: `POST /query/run` validates the request contract and returns `501` until real execution is implemented.

## Sources Checked

Supabase RLS and API exposure behavior were checked against current Supabase documentation and changelog before writing the first migration.
