# Atlante BI

Atlante BI is an AI-powered BI platform for Italian SMBs. This repository starts with the product foundation only: application metadata, strict shared contracts, a technical web shell, and a query-engine boundary.

The current foundation includes SQL Server Technical Snapshot V1,
Queryability Graph V1, and the versioned AI-first Semantic Layer workspace.
It does not yet include query compilation/execution, chart rendering, or
dashboard generation.

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
- immutable technical schema snapshots and queryability graphs
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

The web BFF exposes the connection workflow:

- `GET /connections`
- `GET /connections/new`
- `GET /api/connections`
- `POST /api/connections`
- `POST /api/connections/test`

`POST /api/connections` creates a temporary Secret Manager secret, calls the
query-engine, and saves Supabase metadata even when the test fails so the user
can correct fields without retyping everything. Failed records do not retain a
`secret_ref`; ready records require one.

## Web environment

The web app uses Supabase SSR Auth with cookie-based sessions.

```bash
NEXT_PUBLIC_SUPABASE_URL=https://zzvfjqnfhuvapuvhpxee.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<supabase publishable key>
SUPABASE_SECRET_KEY=<server-only Supabase secret key>
GCP_PROJECT_ID=business-intelligence-495312
QUERY_ENGINE_URL=http://127.0.0.1:8080
QUERY_ENGINE_AUTH_MODE=static_token
QUERY_ENGINE_API_TOKEN=<same non-empty server-only token in web and query-engine>
```

Production query-engine is deployed as a private Cloud Run service:

```bash
QUERY_ENGINE_URL=https://query-engine-3zsxzvizgq-uc.a.run.app
QUERY_ENGINE_AUTH_MODE=google_id_token
QUERY_ENGINE_API_TOKEN=
```

The deployed query-engine uses `QUERY_ENGINE_AUTH_MODE=cloud_run_iam`. Protected
endpoints fail closed unless an internal token or that explicit IAM mode is configured.
The web client accepts only `google_id_token`, `static_token`, or
`local_insecure`; the last option is restricted to loopback URLs outside production.

When the query-engine runs in Cloud Run with the GCP proxy VM, connection
metadata should use the proxy internal IP `10.128.0.2` rather than the proxy
external IP. Local Docker tests can use the external static IP.

Use a Supabase publishable key for the browser/BFF auth flow. `SUPABASE_SECRET_KEY`
is server-only and is used by the BFF to read connection metadata that must not
be exposed through browser-safe views, such as `secret_ref`. Do not put Supabase
secret keys, database passwords, or customer database credentials in `NEXT_PUBLIC_*`
environment variables.

## Services

- Web health: `GET /api/health`
- Web auth: `/login`
- Tenant setup: `/setup`
- Connections: `/connections`
- Schema and Queryability Graph: `/semantic`
- Query engine health: `GET /health`
- Query engine connection test: `POST /connections/test`
- Query engine schema introspection: `POST /schema/introspect`
- Queryability graph compile: `POST /queryability/compile`
- Queryability path search: `POST /queryability/paths`
- Semantic seed: `POST /semantic/seed`
- Semantic AI discovery: `POST /semantic/generate`
- Semantic review and revalidation: `POST /semantic/review`
- Semantic rebase: `POST /semantic/rebase`
- Query engine run boundary: `POST /query/run` validates the request contract and returns `501` until real execution is implemented.

## Semantic discovery environment

The query-engine loads the OpenAI key only at runtime:

```bash
OPENAI_API_KEY=<server-only OpenAI API key>
SEMANTIC_DISCOVERY_MODEL=gpt-5.5
```

`OPENAI_API_KEY` must be provided to Cloud Run through Secret Manager before
enabling live semantic generation. It must not be committed, logged, returned
to the browser, or stored in Supabase. Tests use an injected fake gateway and
do not require network access or an API key.

## Sources Checked

Supabase RLS and API exposure behavior were checked against current Supabase documentation and changelog before writing the first migration.
