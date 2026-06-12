# PRD — Atlante BI

## AI-Powered BI Platform per PMI italiane

### Versione 1.0 — Next.js + Supabase + GCP

---

## 0. Decisioni architetturali vincolanti

Questa versione riparte da zero con scelte più solide.

### Scelte principali

| Area                          | Decisione                                                                   |
| ----------------------------- | --------------------------------------------------------------------------- |
| Frontend                      | Next.js + TypeScript                                                        |
| Backend prodotto              | Next.js BFF/API + servizi separati dove serve                               |
| Query engine                  | Servizio separato su GCP Cloud Run                                          |
| App database                  | Supabase Postgres                                                           |
| Customer database             | Non copiato in Supabase                                                     |
| Customer data warehouse       | Non previsto in V1                                                          |
| Parquet / object storage push | Non previsto in V1                                                          |
| Connessione DB clienti        | Pull live read-only via GCP                                                 |
| Engines V1                    | SQL Server + MySQL                                                          |
| Hosting                       | Google Cloud Platform                                                       |
| Auth                          | Supabase Auth oppure Clerk, con preferenza Supabase Auth per ridurre vendor |
| Metadata app                  | Supabase                                                                    |
| Segreti DB cliente            | GCP Secret Manager                                                          |
| AI runtime                    | Provider singolo configurabile, inizialmente Claude/OpenAI production model |
| Sviluppo                      | GitHub + Codex + CI/CD                                                      |
| Grafici                       | ECharts con compiler deterministico                                         |
| Semantic layer                | Persistente, versionato, arricchito dall’AI ma validato dall’utente         |
| Verification                  | Proporzionale, deterministica, non ansiogena                                |
| MCP runtime                   | Non previsto in V1                                                          |

---

## 1. Visione prodotto

Atlante BI è una webapp multi-tenant che permette a PMI italiane di interrogare il proprio gestionale in linguaggio naturale.

L’utente non tecnico scrive domande come:

* “Mostrami il fatturato 2025 per mese”
* “Quali sono i prodotti più venduti?”
* “Clienti con fatture scadute oltre 90 giorni”
* “Margine per agente commerciale”
* “Confronta vendite 2024 vs 2025”

Il sistema:

1. capisce l’intento;
2. chiede chiarimenti se la domanda è ambigua;
3. genera SQL read-only;
4. esegue la query sul DB cliente;
5. verifica il risultato con query di controllo proporzionate;
6. genera grafico/tabella/KPI;
7. permette di salvare il risultato come widget in dashboard.

Il prodotto non deve sembrare Power BI o Qlik. Deve essere più vicino a Claude, Superpower e Function Health: pulito, editoriale, chiaro, con pochi elementi ma ad alta qualità percepita.

---

## 2. Cosa abbiamo imparato dalla versione precedente

La versione precedente ha mostrato problemi strutturali:

1. L’AI stava decidendo troppe cose insieme: SQL, grafico, formattazione, verifiche, confidence.
2. Il renderer grafici accettava spec fragili.
3. Il verification engine era troppo ansioso: molte verifiche tecniche venivano interpretate come problemi reali sui dati.
4. La confidence numerica generava falsi blocchi.
5. Il sistema non distingueva bene tra:

   * dato errato;
   * verifica non applicabile;
   * errore tecnico del verification engine;
   * privacy finding;
   * join non confermato ma plausibile.
6. Il networking Replit + HAProxy introduceva complessità non necessaria.
7. Supabase rischiava di essere usato impropriamente come deposito dati cliente.
8. L’AI poteva aggiungere colonne non richieste, ad esempio TaxAmt/Freight/TotalDue quando l’utente chiedeva solo fatturato.
9. La formattazione era globale e sbagliava colonne come “numero ordini” mostrandole in valuta.
10. Le CTE e i controlli SQL generati avevano bug specifici di dialect.

La nuova architettura corregge questi punti alla radice.

---

## 3. Obiettivo V1

La V1 deve dimostrare tre cose, non mille:

### 3.1 Connessione sicura a DB cliente

Il cliente fornisce:

* host o IP del DB;
* porta;
* nome database;
* username read-only;
* password;
* eventuale hostname TLS/SNI;
* modalità di rete: allowlist IP pubblico o VPN.

Il sistema si collega in sola lettura.

### 3.2 Domande in linguaggio naturale con risposta visuale

L’utente fa una domanda, ottiene:

* grafico;
* tabella;
* spiegazione breve;
* SQL visibile solo se autorizzato;
* verifiche principali;
* possibilità di salvare in dashboard.

### 3.3 Semantic layer che migliora nel tempo

Il sistema deve imparare il significato business del DB:

* quali tabelle sono utili;
* quali colonne rappresentano fatturato, clienti, ordini, agenti, scadenze;
* quali join sono corretti;
* quali errori sono già stati incontrati;
* quali metriche aziendali sono “stelle polari”.

---

## 4. Fuori scope V1

Non implementare in V1:

* copia completa dei dati cliente;
* data warehouse interno;
* BigQuery;
* Parquet;
* push-based export da server cliente;
* agent installato on-prem;
* MCP runtime;
* multi-provider AI avanzato;
* forecast;
* anomaly detection evoluta;
* semantic layer completamente automatico senza revisione;
* reportistica PDF avanzata;
* mobile app;
* React Native;
* app desktop;
* marketplace connettori.

Queste cose potranno arrivare dopo, ma non ora.

---

## 5. Architettura generale

```txt
┌────────────────────────────────────────────────────────────┐
│                         USER                               │
│                 Browser / Desktop / Tablet                 │
└──────────────────────────────┬─────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────┐
│                    NEXT.JS WEB APP                         │
│                                                            │
│  - UI                                                       │
│  - Auth session                                             │
│  - Dashboard                                                │
│  - Query workspace                                          │
│  - Settings                                                 │
│  - API BFF                                                  │
└──────────────────────────────┬─────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────┐
│                    PRODUCT API / BFF                       │
│                                                            │
│  - tenant middleware                                        │
│  - permission checks                                        │
│  - dashboard/widget API                                     │
│  - query orchestration                                      │
│  - audit log                                                │
│  - calls query-engine                                       │
└───────────────┬────────────────────────────┬───────────────┘
                │                            │
                ▼                            ▼
┌────────────────────────────┐    ┌──────────────────────────┐
│       SUPABASE POSTGRES    │    │   GCP SECRET MANAGER     │
│                            │    │                          │
│ - tenants                  │    │ - DB passwords           │
│ - users                    │    │ - API keys               │
│ - permissions              │    │ - connection secrets     │
│ - dashboards               │    │                          │
│ - widgets                  │    └──────────────────────────┘
│ - semantic layer           │
│ - query history metadata   │
│ - optional widget cache    │
└────────────────────────────┘

                               │ internal HTTPS
                               ▼
┌────────────────────────────────────────────────────────────┐
│                  QUERY ENGINE — CLOUD RUN                  │
│                                                            │
│  Python / FastAPI                                          │
│  - SQL Server adapter                                      │
│  - MySQL adapter                                           │
│  - schema introspection                                    │
│  - SQL validation with sqlglot                             │
│  - query execution                                         │
│  - result profiling                                        │
│  - verification checks                                     │
│  - chart compiler inputs                                   │
└──────────────────────────────┬─────────────────────────────┘
                               │
               ┌───────────────┴────────────────┐
               │                                │
               ▼                                ▼
┌────────────────────────────┐    ┌──────────────────────────┐
│ Public allowlist mode      │    │ VPN mode                 │
│                            │    │                          │
│ Cloud Run → VPC Connector  │    │ Cloud Run → VPC          │
│ → Cloud NAT static IP      │    │ → Cloud VPN / gateway    │
│ → Customer DB public host  │    │ → Customer private DB    │
└────────────────────────────┘    └──────────────────────────┘
```

---

## 6. Perché Next.js

Next.js è corretto per questo prodotto perché:

* è una webapp business desktop-first;
* serve rendering veloce e UX ricca;
* supporta routing, layout, server components, API/BFF;
* si integra bene con Supabase, Vercel/GCP/GitHub;
* usa React, quindi ecosistema UI enorme;
* è più adatto di React Native, che serve per app mobile native;
* è più flessibile di Angular per prototipare UI moderne e custom.

Angular non è sbagliato in assoluto, ma per questo prodotto aumenterebbe rigidità e velocità di sviluppo inferiore. React Native è proprio il target sbagliato: qui serve una BI web, non un’app mobile.

---

## 7. Stack tecnico

### 7.1 Frontend

| Area                   | Tecnologia                 |
| ---------------------- | -------------------------- |
| Framework              | Next.js App Router         |
| Linguaggio             | TypeScript                 |
| Styling                | Tailwind CSS               |
| UI system              | shadcn/ui + Radix UI       |
| Motion                 | Framer Motion              |
| Grafici                | Apache ECharts             |
| Tabelle                | TanStack Table             |
| Query client           | TanStack Query             |
| Form                   | React Hook Form            |
| Validazione            | Zod                        |
| Stato UI leggero       | Zustand, solo se serve     |
| Date/number formatting | Intl API + utility interne |

### 7.2 Backend prodotto

| Area          | Tecnologia                                           |
| ------------- | ---------------------------------------------------- |
| API/BFF       | Next.js Route Handlers oppure servizio Node separato |
| Auth          | Supabase Auth, alternativa Clerk                     |
| DB app        | Supabase Postgres                                    |
| ORM           | Drizzle ORM oppure Prisma                            |
| Audit/logging | Supabase + Cloud Logging                             |
| Jobs          | Cloud Scheduler + Cloud Tasks                        |
| Secrets       | GCP Secret Manager                                   |

### 7.3 Query engine

| Area                   | Tecnologia                            |
| ---------------------- | ------------------------------------- |
| Runtime                | Python                                |
| Framework              | FastAPI                               |
| SQL parsing/validation | sqlglot                               |
| SQL Server driver      | Microsoft ODBC Driver 18 via pyodbc   |
| MySQL driver           | mysql-connector-python oppure PyMySQL |
| Dataframe leggero      | pandas solo dove utile                |
| Deployment             | GCP Cloud Run                         |
| Networking             | VPC Connector + Cloud NAT / VPN       |

Motivo della separazione: il query engine è il cuore delicato del prodotto. Deve gestire dialect SQL, introspection, verifica query, TLS, timeout e connessioni DB. Tenerlo separato dalla UI evita un monolite fragile.

---

## 8. Supabase: cosa salva e cosa non salva

Supabase salva dati applicativi, non il database cliente.

### 8.1 Supabase salva

* tenant;
* utenti;
* permessi;
* connessioni, senza password;
* riferimenti ai segreti in GCP Secret Manager;
* dashboard;
* widget;
* semantic layer;
* query history;
* audit log;
* memorie semantiche;
* business anchors;
* eventuali cache aggregate dei widget.

### 8.2 Supabase non salva

* dump del DB cliente;
* tabelle cliente replicate;
* dati grezzi completi;
* password DB in chiaro;
* file Parquet;
* warehouse analitico.

### 8.3 Cache widget

Per far caricare rapidamente dashboard già salvate, si può salvare una cache piccola e controllata del risultato del widget.

Default V1:

* massimo 500 righe per widget;
* solo risultato aggregato già mostrato in UI;
* retention configurabile;
* disattivabile per tenant;
* mai usata come copia completa del DB cliente.

Se un cliente vieta qualsiasi salvataggio dati, il widget viene ricalcolato live a ogni apertura.

---

## 9. Networking e connessione ai DB clienti

### 9.1 Modalità A — Public endpoint con IP allowlist

Percorso:

```txt
Cloud Run Query Engine
→ VPC Connector
→ Cloud NAT con IP statico
→ DB cliente pubblico con firewall allowlist
```

Il cliente whitelista l’IP statico GCP.

Requisiti:

* utente DB read-only;
* TLS attivo;
* password robusta;
* accesso limitato a schema/view BI;
* audit lato cliente consigliato.

Questa modalità è semplice ma non ideale per tutti.

### 9.2 Modalità B — VPN site-to-site

Percorso:

```txt
Cloud Run Query Engine
→ VPC Connector
→ VPC GCP
→ Cloud VPN / gateway
→ rete privata cliente
→ DB privato cliente
```

Questa è la modalità consigliata per clienti più strutturati.

Preferenza tecnica:

1. IPsec site-to-site con Cloud VPN quando possibile.
2. WireGuard gateway VM solo se il cliente supporta esclusivamente WireGuard.
3. No esposizione SQL Server su Internet quando l’IT del cliente la vieta.

### 9.3 Modalità C — Customer-side agent

Non in V1.

Sarebbe un agente installato dal cliente che:

* legge il DB localmente;
* invia dati aggregati o estratti;
* evita inbound verso la rete cliente.

È sensato in futuro, ma in V1 aumenterebbe troppo lo scope.

---

## 10. Requisiti DB cliente

### 10.1 SQL Server

Accesso minimo consigliato:

```sql
GRANT CONNECT TO atlante_bi_ro;
ALTER ROLE db_datareader ADD MEMBER atlante_bi_ro;
```

Meglio ancora:

* creare schema o viste dedicate;
* concedere SELECT solo su quelle viste;
* evitare accesso a tabelle non rilevanti;
* impedire EXEC su stored procedure;
* impedire DDL/DML.

Per introspection servono permessi di lettura su:

* `INFORMATION_SCHEMA.TABLES`
* `INFORMATION_SCHEMA.COLUMNS`
* `INFORMATION_SCHEMA.KEY_COLUMN_USAGE`
* `INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS`
* `sys.tables`
* `sys.columns`
* `sys.foreign_keys`
* `sys.foreign_key_columns`
* `sys.indexes`
* `sys.index_columns`
* viste/tabelle incluse nel perimetro BI

### 10.2 MySQL

Accesso minimo consigliato:

```sql
GRANT SELECT, SHOW VIEW ON database_name.* TO 'atlante_bi_ro'@'%';
```

Per introspection servono:

* `information_schema.tables`
* `information_schema.columns`
* `information_schema.key_column_usage`
* `information_schema.referential_constraints`
* `information_schema.statistics`

### 10.3 Nome database obbligatorio

Sì, in V1 il nome database è obbligatorio.

Motivo: serve per introspection, scope, sicurezza, validazione tabelle e prevenzione cross-database query.

---

## 11. TLS e sicurezza connessioni

### 11.1 Regola generale

Tutte le connessioni devono usare TLS quando supportato.

### 11.2 SQL Server

Usare ODBC Driver 18 con:

* `Encrypt=yes`;
* `TrustServerCertificate=no` di default;
* `ServerCertificate` / hostname validation quando supportato;
* `tls_server_name` separato se si passa da proxy/VPN/gateway.

### 11.3 MySQL

Usare TLS con:

* `ssl_mode=VERIFY_IDENTITY` quando possibile;
* CA certificate configurabile;
* fallback a `REQUIRED` solo con warning esplicito.

### 11.4 TrustServerCertificate

Consentito solo come eccezione temporanea.

La UI deve mostrare:

> Certificato non verificato — configurazione sconsigliata.

Non deve essere il default.

---

## 12. Auth, tenant e permessi

### 12.1 Ruoli

| Ruolo   | Descrizione                                   |
| ------- | --------------------------------------------- |
| owner   | gestisce tenant, billing, connessioni, utenti |
| admin   | gestisce semantic layer, dashboard, utenti    |
| analyst | può fare query e creare dashboard             |
| viewer  | può solo vedere dashboard condivise           |

### 12.2 Permessi granulari

Permessi separati:

* `connection.manage`
* `semantic.manage`
* `query.run`
* `query.view_sql`
* `query.manual_sql`
* `dashboard.create`
* `dashboard.edit`
* `widget.edit`
* `team.manage`
* `settings.manage`
* `business_anchor.manage`

### 12.3 Isolamento tenant

Ogni tabella app ha `tenant_id`.

Usare:

* middleware applicativo;
* policy RLS su Supabase dove possibile;
* audit log per ogni accesso sensibile.

---

## 13. Data model principale

### 13.1 tenants

```txt
id uuid pk
name text
slug text unique
plan text
status text
created_at timestamptz
updated_at timestamptz
```

### 13.2 tenant_users

```txt
id uuid pk
tenant_id uuid fk
auth_user_id text
email text
display_name text
role text
is_active boolean
created_at timestamptz
updated_at timestamptz
```

### 13.3 db_connections

```txt
id uuid pk
tenant_id uuid fk
label text
engine text -- sqlserver | mysql
network_mode text -- public_allowlist | vpn
host text
port integer
database_name text
username text
secret_ref text -- GCP Secret Manager reference
ssl_enabled boolean
tls_server_name text nullable
trust_server_certificate boolean default false
vpn_profile_id uuid nullable
status text -- draft | active | error | disabled
last_test_status text
last_test_at timestamptz
created_by uuid
created_at timestamptz
updated_at timestamptz
```

Password e credenziali non stanno in Supabase.

### 13.4 vpn_profiles

```txt
id uuid pk
tenant_id uuid fk
label text
type text -- ipsec | wireguard_gateway
gcp_resource_ref text
customer_subnet text
status text
created_at timestamptz
updated_at timestamptz
```

### 13.5 schema_snapshots

```txt
id uuid pk
tenant_id uuid fk
connection_id uuid fk
schema_hash text
snapshot_hash text
snapshot jsonb
summary jsonb
table_count integer
column_count integer
coverage_status text -- ok | partial | warning | blocked
created_at timestamptz
```

### 13.6 queryability_graph_versions

Artefatto tecnico immutabile derivato da uno snapshot.

```txt
id uuid pk
tenant_id uuid fk
connection_id uuid fk
schema_snapshot_id uuid fk
version integer
contract_version text -- queryability_graph.v1
builder_version text
policy_version text
status text -- complete | partial
schema_hash text
snapshot_hash text
graph_input_hash text
derivation_key text
graph_hash text
graph jsonb
node_count integer
column_count integer
edge_count integer
created_by uuid
created_at timestamptz
```

Nodi, colonne ed edge sono anche proiettati in tabelle normalizzate per API,
diagnostica e path finding. Il lineage delle view e le FK sono edge distinti.
Solo gli edge `fk_join` possono essere usati per routing automatico.

### 13.7 semantic_layer_versions

```txt
id uuid pk
tenant_id uuid fk
connection_id uuid fk
queryability_graph_version_id uuid fk
base_graph_hash text
version integer
status text -- draft | active | archived
created_by uuid
created_at timestamptz
activated_at timestamptz nullable
```

La versione semantica e' `fresh` quando `base_graph_hash` coincide con il
graph corrente, `stale` quando differisce e `indeterminate` quando l'ultimo
build del graph e' blocked.

### 13.8 semantic_tables

```txt
id uuid pk
tenant_id uuid fk
semantic_version_id uuid fk
schema_name text
table_name text
object_type text -- table | view
display_name text
description text
included boolean
business_domain text nullable
row_count_approx bigint nullable
confidence text
created_at timestamptz
updated_at timestamptz
```

### 13.9 semantic_columns

```txt
id uuid pk
tenant_id uuid fk
semantic_table_id uuid fk
column_name text
display_name text
description text
data_type text
semantic_type text -- money | quantity | id | date | customer | product | etc.
is_nullable boolean
is_primary_key boolean
is_foreign_key boolean
included boolean
pii_kind text nullable
format_hint text nullable -- currency | integer | decimal | percent | date | text
created_at timestamptz
updated_at timestamptz
```

### 13.10 semantic_relationships

```txt
id uuid pk
tenant_id uuid fk
semantic_version_id uuid fk
from_table_id uuid
from_column_id uuid
to_table_id uuid
to_column_id uuid
relationship_type text -- one_to_many | many_to_one | one_to_one
source text -- graph_edge | inferred | user_confirmed | ai_suggested
graph_edge_id uuid nullable
confidence numeric
status text -- proposed | verified | rejected
evidence jsonb
created_at timestamptz
updated_at timestamptz
```

### 13.11 semantic_metrics

```txt
id uuid pk
tenant_id uuid fk
semantic_version_id uuid fk
name text -- fatturato, margine, ordini, clienti_attivi
description text
source_table_id uuid
measure_column_id uuid nullable
aggregation text -- sum | count | count_distinct | avg
grain text -- order | order_line | invoice | customer | product
default_date_column_id uuid nullable
default_filters jsonb
synonyms text[]
status text -- proposed | verified | deprecated
created_at timestamptz
updated_at timestamptz
```

### 13.12 semantic_memory

```txt
id uuid pk
tenant_id uuid fk
connection_id uuid fk
semantic_version_id uuid fk
memory_type text -- join_rule | metric_rule | query_fix | ambiguity_rule | warning
title text
content text
evidence jsonb
related_tables text[]
related_columns text[]
status text -- proposed | verified | user_confirmed | deprecated
hit_count integer
last_used_at timestamptz nullable
schema_hash text
created_at timestamptz
updated_at timestamptz
```

### 13.13 business_anchors

Le “stelle polari”.

```txt
id uuid pk
tenant_id uuid fk
name text -- fatturato_2025, numero_clienti_attivi, ordini_anno
metric_name text
period_start date nullable
period_end date nullable
value numeric
unit text -- EUR | count | percent | etc.
tolerance_percent numeric default 5
source text -- manual | imported
status text -- active | archived
created_by uuid
created_at timestamptz
updated_at timestamptz
```

Esempio:

```txt
metric_name = fatturato
period_start = 2025-01-01
period_end = 2025-12-31
value = 10000000
unit = EUR
tolerance_percent = 5
```

Questi valori possono essere passati all’AI in forma sintetica e usati anche deterministicamente per controlli di plausibilità.

### 13.14 dashboards

```txt
id uuid pk
tenant_id uuid fk
parent_id uuid nullable
name text
icon text nullable
sort_order integer
created_by uuid
created_at timestamptz
updated_at timestamptz
```

### 13.15 widgets

Un widget è l’oggetto salvato che contiene domanda, SQL, grafico, impostazioni e refresh.

```txt
id uuid pk
tenant_id uuid fk
connection_id uuid fk
title text
natural_language_query text nullable
generated_sql text
query_source text -- ai | manual
chart_spec jsonb
display_config jsonb
auto_refresh_minutes integer nullable
created_by uuid
created_at timestamptz
updated_at timestamptz
```

### 13.16 dashboard_widgets

Permette lo stesso widget su più dashboard senza duplicarlo.

```txt
id uuid pk
tenant_id uuid fk
dashboard_id uuid fk
widget_id uuid fk
position jsonb
created_at timestamptz
updated_at timestamptz
unique(dashboard_id, widget_id)
```

Se un widget è presente in più dashboard, quando l’utente lo elimina la UI deve chiedere:

* rimuovi solo da questa dashboard;
* rimuovi da più dashboard selezionate;
* elimina definitivamente il widget.

### 13.17 widget_cache

```txt
id uuid pk
tenant_id uuid fk
widget_id uuid fk
data jsonb
row_count integer
data_hash text
cached_at timestamptz
expires_at timestamptz nullable
```

Disattivabile per tenant.

### 13.18 query_runs

```txt
id uuid pk
tenant_id uuid fk
user_id uuid fk
connection_id uuid fk
natural_language_query text
clarified_query text nullable
generated_sql text
chart_spec jsonb
status text -- success | blocked | failed | needs_clarification
result_row_count integer
execution_ms integer
confidence_label text -- verified | plausible | to_verify | blocked
confidence_score numeric nullable -- internal, not shown by default
created_at timestamptz
```

### 13.19 query_checks

```txt
id uuid pk
tenant_id uuid fk
query_run_id uuid fk
check_type text
status text -- pass | warn | fail | skip | engine_error
severity text -- info | warning | error
message text
control_sql text nullable
expected_value numeric nullable
actual_value numeric nullable
details jsonb
execution_ms integer nullable
created_at timestamptz
```

### 13.20 audit_log

```txt
id uuid pk
tenant_id uuid fk
user_id uuid nullable
action text
entity_type text nullable
entity_id uuid nullable
severity text -- info | warning | critical
metadata jsonb
ip_address text nullable
created_at timestamptz
```

---

## 14. Queryability Graph e Semantic Layer

Il semantic layer è il cuore del prodotto.

### 14.1 Queryability Graph V1

Pipeline obbligatoria:

```txt
Technical Snapshot V1
-> Queryability Graph V1
-> Semantic Layer
-> Query Compiler
```

Il graph e' tecnico, deterministico, tenant-scoped e immutabile. Contiene
nodi table/view, colonne queryable o escluse, candidate keys, FK direzionali,
nullability, stati trusted/disabled, self-reference, bridge candidate e
lineage view.

Solo `fk_join` puo' essere usato per routing automatico. FK disabled o
untrusted restano metadata ma sono escluse dai path automatici. Il lineage
view non dimostra predicati di join e le indexed view non propagano chiavi
alle tabelle sorgenti.

Path finding V1:

* massimo quattro hop;
* shortest path equivalenti producono `ambiguous`;
* espansioni parent -> child producono warning fanout.

Stati:

* `complete`: routing tecnico pienamente utilizzabile;
* `partial`: routing utilizzabile con metadata non bloccanti incompleti;
* `blocked`: graph non utilizzabile e import non persistito.

Hash:

* `schema_hash`: DDL stabile osservabile;
* `snapshot_hash`: snapshot tecnico full-fidelity;
* `graph_input_hash`: soli campi consumati dal builder;
* `graph_hash`: output canonico del graph.

Derivation key:

```txt
graph_input_hash + builder_version + policy_version
```

### 14.2 Build iniziale del Semantic Layer

L'import schema termina con `semantic_status = not_initialized`. La mancanza
del Semantic Layer dopo un import riuscito non e' un errore.

La creazione successiva:

1. seleziona una versione Queryability Graph;
2. salva `base_graph_hash`;
3. aggiunge naming, metriche e interpretazioni business;
4. applica eventuale AI enrichment;
5. richiede revisione admin;
6. attiva esplicitamente la versione.

La freshness dipende da `base_graph_hash`, non da `schema_hash`.

### 14.3 Profiling privacy-safe

Il sistema può calcolare internamente:

* count righe;
* null ratio;
* min/max;
* distinct count approssimato;
* pattern su stringhe;
* lunghezza media;
* valori numerici aggregati.

Non deve inviare dati raw all’AI di default.

Opzione tenant:

```txt
ai_send_sample_rows = false default
```

Se attivata, inviare solo sample redatti e limitati.

### 14.4 AI enrichment

L’AI può suggerire:

* display name italiano;
* descrizione business;
* dominio;
* metriche candidate;
* join candidate;
* colonne da escludere;
* sinonimi business.

L’AI non decide in modo definitivo. Il semantic layer attivo deve essere revisionabile.

### 14.5 Memorie semantiche

Quando il sistema scopre qualcosa di utile, crea memoria.

Esempi:

* “fatturato = SubTotal su SalesOrderHeader, non TotalDue”
* “SalesOrderDetail.LineTotal riconcilia con SalesOrderHeader.SubTotal”
* “ProductCategory è gerarchica tramite ParentProductCategoryID”
* “documenti è ambiguo: chiedere se fatture, DDT, ordini, note credito”
* “non usare ShipDate per fatturato salvo richiesta esplicita”

Le memorie sono:

* proposte automaticamente;
* usate nei prompt;
* tracciate con hit_count;
* deprecate se cambia schema;
* promosse se confermate o usate con successo.

---

## 15. Business anchors / Stelle polari

Le stelle polari sono valori guida inseriti dall’utente/admin.

Esempi:

* fatturato 2025 = 10.000.000 €
* clienti attivi 2025 = 1.250
* ordini 2025 = 18.300
* magazzino medio = 2.400.000 €

### 15.1 A cosa servono

Servono a intercettare errori grossolani.

Esempio:

* utente chiede: “mostrami il fatturato 2025”
* query primaria produce 100.000.000 €
* stella polare dice 10.000.000 €
* il sistema deve sospettare:

  * join duplicativo;
  * somma su righe invece che testate;
  * inclusione IVA/spese;
  * periodo errato;
  * valuta errata;
  * documenti doppi.

### 15.2 Come vengono usate

Le stelle polari vanno incluse nel contesto AI in forma sintetica.

Esempio prompt context:

```json
{
  "business_anchors": [
    {
      "metric": "fatturato",
      "period": "2025",
      "value": 10000000,
      "unit": "EUR",
      "tolerance_percent": 5
    }
  ]
}
```

In parallelo, il sistema fa anche controllo deterministico quando la metrica e il periodo sono compatibili.

### 15.3 Importante

La stella polare non sostituisce la query.

È un controllo di plausibilità, non una fonte dati primaria.

---

## 16. Query pipeline

### 16.1 Fase 1 — Intent planner

Input:

* domanda utente;
* semantic layer;
* memorie rilevanti;
* business anchors;
* permessi utente;
* connessione attiva.

Output strutturato:

```json
{
  "status": "ready | needs_clarification",
  "intent": "...",
  "metric": "...",
  "dimensions": [],
  "filters": [],
  "time_range": null,
  "requested_chart_type": null,
  "ambiguities": [],
  "clarifying_question": null,
  "options": []
}
```

### 16.2 Ambiguità

Se la domanda è ambigua, il sistema deve chiedere.

Esempio:

> “Mostrami il totale documenti 2024”

Domanda da fare:

> “Per documenti intendi fatture, ordini, DDT, note credito o tutti i documenti commerciali?”

Non deve indovinare.

### 16.3 Fase 2 — SQL generation

L’AI genera SQL solo dopo intent chiaro.

Regole:

* solo SELECT;
* niente INSERT/UPDATE/DELETE;
* niente DDL;
* niente EXEC;
* niente stored procedure;
* niente cross-database;
* usare solo tabelle/colonne incluse nel semantic layer;
* rispettare metriche verificate;
* non aggiungere colonne non richieste.

Esempio regola importante:

Se l’utente chiede “fatturato”, e il semantic layer dice che fatturato = SubTotal, il SELECT deve includere:

* periodo;
* fatturato;
* al massimo numero ordini come contesto.

Non deve aggiungere automaticamente:

* IVA;
* spedizione;
* TotalDue;
* cumulati;
* margini;
* colonne accessorie.

### 16.4 Fase 3 — SQL validation

Il query engine valida SQL con:

* sqlglot;
* dialect specifico;
* allowlist statement;
* table allowlist;
* column allowlist;
* blacklist difensiva;
* timeout;
* row limit;
* statement singolo.

### 16.5 Fase 4 — Execution

Default:

* timeout 30s;
* row limit 5.000;
* result payload max configurabile;
* read-only DB user;
* connessione pool per tenant/connection;
* retry solo su errori transienti, mai su errori SQL logici.

### 16.6 Fase 5 — Verification

Verification proporzionale, non ansiosa.

#### Always-on checks

* static validation;
* tables in semantic layer;
* columns in semantic layer;
* dry run;
* row count sanity;
* null/negative sanity su misura principale;
* duplicate output rows solo se utile.

#### Aggregation checks

Per SUM additive:

* total vs breakdown;
* header/detail reconciliation se join 1:N;
* join amplification;
* business anchor plausibility se disponibile.

#### Skip onesto

Se un controllo non è applicabile:

```txt
status = skip
severity = info
```

Non deve penalizzare la confidence.

#### Engine error

Se il verification engine genera una query di controllo non valida:

```txt
status = engine_error
severity = info/warning
```

Non deve essere confuso con dato errato.

### 16.7 Fase 6 — Result policy

Il risultato viene bloccato solo se:

* SQL non sicuro;
* query primaria fallisce;
* tabelle fuori layer;
* permessi insufficienti;
* verifica critica rileva contraddizione forte;
* risultato troppo grande;
* connessione DB non sicura per policy tenant.

Non bloccare per:

* skip;
* privacy finding;
* engine error del controllo;
* join non confermato ma runtime checks passati;
* mancanza baseline storica;
* mancanza business anchor.

---

## 17. Confidence

Non mostrare percentuale precisa all’utente business di default.

Mostrare label:

| Label         | Significato                                       |
| ------------- | ------------------------------------------------- |
| Verificato    | controlli principali passati                      |
| Plausibile    | risultato buono, alcuni controlli non applicabili |
| Da verificare | risultato mostrato ma richiede revisione          |
| Bloccato      | risultato non mostrabile                          |

La percentuale può stare in modalità debug/admin.

Motivo: un “86%” sembra scientifico ma spesso è solo scoring euristico. Meglio label onesta + motivazioni.

---

## 18. Chart system

### 18.1 Principio

L’AI non deve renderizzare il grafico.

L’AI propone:

* tipo grafico richiesto o consigliato;
* campo X;
* campo Y;
* eventuali serie;
* titolo.

Il Chart Compiler deterministico valida e normalizza.

### 18.2 ChartSpec

```json
{
  "type": "bar",
  "title": "Fatturato mensile 2025",
  "encoding": {
    "x": "mese",
    "y": "fatturato",
    "series": null
  },
  "format": {
    "column_formats": {
      "mese": { "type": "date_bucket" },
      "fatturato": { "type": "currency", "currency": "EUR", "decimals": 2 },
      "numero_ordini": { "type": "integer" }
    }
  },
  "display": {
    "show_legend": true,
    "show_data_labels": false,
    "sort": "x_asc",
    "limit": 20
  }
}
```

### 18.3 Tipi supportati V1

* table;
* KPI number;
* bar;
* horizontal bar;
* grouped bar;
* stacked bar;
* line;
* area;
* combo bar + line;
* pie;
* donut;
* scatter.

Ogni tipo deve avere mapping ECharts testato.

Se il tipo richiesto dall’utente è supportato, deve renderizzare. “Tipo di grafico non supportato: bar” è un bug bloccante.

### 18.4 Chart compiler

Input:

* rows;
* columns;
* chart_spec AI;
* semantic column hints;
* user requested chart type.

Output:

* chart_spec normalizzato;
* ECharts option;
* warning non bloccanti.

Regole:

* se manca x/y, derivare default sensato;
* se y punta a colonna inesistente, scegliere prima misura numerica compatibile;
* se ci sono troppe serie, passare a tabella o top-N;
* se il grafico non ha senso, mostrare tabella con spiegazione;
* non formattare tutte le colonne numeriche come valuta.

### 18.5 Formattazione colonne

Deterministica.

Regole base:

| Tipo colonna                             | Formato           |
| ---------------------------------------- | ----------------- |
| mese, anno, periodo                      | testo/date bucket |
| numero_ordini, count                     | intero            |
| quantità                                 | intero o decimale |
| fatturato, imponibile, totale, subtotale | valuta            |
| percentuale, ratio                       | percentuale       |
| codice, id, numero documento             | testo             |
| data                                     | data              |

La formattazione AI è solo hint. Il sistema deve poter correggere.

---

## 19. Widget

Un widget è una query salvata con visualizzazione.

Contiene:

* domanda originale;
* SQL generato;
* chart_spec;
* impostazioni di visualizzazione;
* refresh policy;
* cache opzionale;
* permessi.

### 19.1 Copia su dashboard

Lo stesso widget può apparire su più dashboard tramite `dashboard_widgets`.

Non duplicare query, SQL e refresh.

### 19.2 Eliminazione widget

Se widget appare su più dashboard:

* rimuovi solo da questa dashboard;
* rimuovi da dashboard selezionate;
* elimina definitivamente.

### 19.3 Impostazioni widget

Ogni widget deve permettere:

* rinomina;
* modifica grafico tramite AI;
* modifica campi X/Y;
* cambio tipo grafico;
* visualizzazione SQL;
* export CSV/XLSX;
* refresh manuale;
* auto-refresh;
* duplicazione intenzionale;
* copia su altra dashboard.

### 19.4 Modifica grafico con AI

Quando l’utente dice:

> “fammi questo come linea invece che barre”

L’AI deve ricevere:

* query originale;
* SQL;
* colonne risultato;
* chart_spec attuale;
* richiesta utente.

Non deve rigenerare SQL se cambia solo il grafico.

---

## 20. UX/UI

### 20.1 Direzione visiva

Stile:

* pulito;
* dark mode raffinata;
* poche card;
* ampi spazi;
* tipografia forte;
* animazioni leggere;
* niente look enterprise anni 2000;
* niente dashboard iper-cariche.

I riferimenti sono:

* Claude;
* Superpower;
* Function Health.

Non copiare, ma prendere:

* chiarezza;
* ritmo visivo;
* qualità editoriale;
* minimalismo premium.

### 20.2 Layout principale

Sidebar sinistra:

* Esplora;
* Dashboard;
* Semantic Layer;
* Connessioni;
* Team;
* Impostazioni.

Topbar:

* tenant switcher;
* status connessione;
* user menu.

Workspace centrale:

* input domanda;
* risultato;
* grafico;
* tabella;
* verifiche;
* salva widget.

### 20.3 Query workspace

Stato iniziale:

```txt
Chiedi qualcosa ai tuoi dati…
```

Esempi contestuali presi dal semantic layer:

* “Fatturato per mese”
* “Top clienti per vendite”
* “Prodotti più venduti”
* “Fatture scadute”
* “Vendite per agente”

### 20.4 Clarifying question

Se ambiguo:

```txt
Prima di procedere, chiarisco una cosa.

Per “documenti” intendi:
[ Fatture ] [ Ordini ] [ DDT ] [ Note credito ] [ Tutti ]
```

L’utente deve scegliere o scrivere.

### 20.5 Verification drawer

Mostrare sezioni separate:

1. Query
2. Controlli eseguiti
3. Controlli non applicabili
4. Warning reali
5. Privacy
6. SQL

Privacy non deve stare tra le verifiche matematiche.

### 20.6 Errori

Pattern:

```txt
Cosa è successo
Perché può essere successo
Cosa puoi fare
```

Mai messaggi tipo stack trace o codice driver grezzo.

---

## 21. Privacy

### 21.1 PII non penalizza confidence

La presenza di dati personali non significa che la query è sbagliata.

PII serve per:

* redazione sample verso AI;
* warning privacy;
* export policy;
* audit;
* permessi futuri.

Non deve abbassare score o nascondere risultato.

### 21.2 PII detection

Flaggare:

* nome;
* cognome;
* email;
* telefono;
* codice fiscale;
* partita IVA se persona fisica;
* IBAN;
* indirizzo;
* data nascita.

Non flaggare come PII di default:

* ID tecnici;
* SalesOrderID;
* numero ordine;
* numero fattura;
* data ordine;
* data documento;
* SubTotal;
* fatturato;
* imponibile;
* quantità.

---

## 22. AI runtime

### 22.1 Uso AI

L’AI viene usata per:

* interpretare domanda;
* chiedere chiarimenti;
* proporre SQL;
* spiegare risultato;
* suggerire chart_spec;
* arricchire semantic layer;
* creare memorie;
* rispondere a domande sul grafico.

### 22.2 Cosa non deve fare da sola

L’AI non deve essere unica fonte di verità per:

* sicurezza SQL;
* permessi;
* chart rendering;
* confidence finale;
* formattazione colonne;
* accesso a tabelle;
* validazione tenant;
* business anchor check.

### 22.3 Prompt contract

Output AI sempre JSON strutturato.

Esempio:

```json
{
  "intent": "fatturato mensile",
  "needs_clarification": false,
  "sql": "...",
  "assumptions": [],
  "chart": {
    "type": "bar",
    "x": "mese",
    "y": "fatturato"
  },
  "verification_plan": [
    {
      "type": "total_vs_breakdown",
      "purpose": "Confronta somma mensile con totale diretto"
    }
  ]
}
```

### 22.4 AI su dati risultato

L’AI può analizzare i dati restituiti dalla query quando l’utente chiede:

* “spiegami questo grafico”;
* “cosa noti?”;
* “perché giugno è alto?”;
* “fammi insight”.

Limiti:

* inviare massimo N righe;
* preferire aggregati;
* redigere PII;
* rispettare policy tenant.

---

## 23. Verification engine

### 23.1 Filosofia

Il verification engine deve aiutare, non sabotare.

Non deve trasformare ogni assenza di contesto in problema.

### 23.2 Stati

| Stato        | Significato                  |
| ------------ | ---------------------------- |
| pass         | controllo superato           |
| warn         | possibile problema reale     |
| fail         | problema forte               |
| skip         | non applicabile              |
| engine_error | errore tecnico del controllo |

### 23.3 Regole confidence

Non penalizzare:

* skip;
* privacy finding;
* engine error;
* mancanza baseline;
* mancanza business anchor.

Penalizzare:

* tabella fuori layer;
* colonna inesistente;
* SQL non sicuro;
* risultato vuoto inatteso;
* null/negativi su metrica dove non ammessi;
* join amplification reale;
* business anchor mismatch forte;
* total vs breakdown mismatch.

### 23.4 Controlli V1

* static validation;
* tables in layer;
* columns in layer;
* dry run;
* row count sanity;
* null/negative sanity;
* duplicate output rows;
* join amplification;
* total vs breakdown;
* header/detail reconciliation;
* business anchor plausibility;
* metric consistency se metrica ha grain;
* historical plausibility solo se baseline disponibile.

---

## 24. Rate limit e cost control

### 24.1 Rate limit

Per tenant:

* query AI/minuto;
* query DB/minuto;
* schema introspection/giorno;
* refresh widget/ora.

### 24.2 AI budget

Tracciare:

* input tokens;
* output tokens;
* costo stimato;
* costo giornaliero tenant;
* costo mensile tenant.

Stop automatico se supera budget.

### 24.3 Query budget

Ogni domanda ha budget:

| Tipo query               | Max control query       |
| ------------------------ | ----------------------- |
| lookup semplice          | 1-2                     |
| aggregazione semplice    | 2-4                     |
| join + aggregazione      | 4-6                     |
| business anchor mismatch | +2 debug query          |
| ambigua                  | zero, prima chiarimento |

---

## 25. Refresh dashboard

Auto-refresh server-side.

Componenti:

* Cloud Scheduler;
* Cloud Tasks;
* query engine;
* widget_cache;
* audit log.

Intervalli V1:

* manuale;
* 15 minuti;
* 30 minuti;
* 1 ora;
* 4 ore;
* 24 ore.

Rate limit per tenant.

Se il DB non è raggiungibile:

* mostra cache precedente;
* badge “dati non aggiornati”;
* notifica admin;
* non martellare il DB.

---

## 26. API principali

### Connessioni

```txt
POST /api/connections/test
POST /api/connections
GET  /api/connections
GET  /api/connections/:id
PATCH /api/connections/:id
DELETE /api/connections/:id
```

### Schema / semantic

```txt
POST /api/schema/introspect
POST /api/semantic/build
GET  /api/semantic
PATCH /api/semantic/tables/:id
PATCH /api/semantic/columns/:id
POST /api/semantic/activate
```

### Query

```txt
POST /api/query/plan
POST /api/query/run
POST /api/query/clarify
POST /api/query/:id/ask
GET  /api/query/history
```

### Dashboard

```txt
GET    /api/dashboards
POST   /api/dashboards
GET    /api/dashboards/:id
PATCH  /api/dashboards/:id
DELETE /api/dashboards/:id
```

### Widget

```txt
POST   /api/widgets
GET    /api/widgets/:id
PATCH  /api/widgets/:id
DELETE /api/widgets/:id
POST   /api/widgets/:id/refresh
POST   /api/widgets/:id/copy-to-dashboard
POST   /api/widgets/:id/detach
POST   /api/widgets/:id/ask
```

### Business anchors

```txt
GET    /api/business-anchors
POST   /api/business-anchors
PATCH  /api/business-anchors/:id
DELETE /api/business-anchors/:id
```

---

## 27. Pagine frontend

### 27.1 `/login`

Login Supabase/Clerk.

### 27.2 `/setup`

Creazione tenant.

### 27.3 `/connections/new`

Wizard connessione:

1. engine;
2. network mode;
3. host/porta/database;
4. TLS;
5. credenziali;
6. test;
7. salva.

### 27.4 `/semantic`

Semantic layer admin:

* lista tabelle;
* ricerca;
* filtri;
* colonne;
* relazioni;
* metriche;
* memorie;
* stelle polari.

Deve reggere migliaia di tabelle con virtualizzazione.

### 27.5 `/query`

Workspace domande.

### 27.6 `/dashboards`

Indice dashboard.

### 27.7 `/dashboard/:id`

Dashboard con grid widget.

### 27.8 `/settings`

Tenant settings:

* piano;
* sicurezza;
* privacy;
* cache;
* AI usage;
* networking;
* team.

---

## 28. Testing

Non serve obbligare test locale nella V1.

Testing previsto:

### 28.1 CI GitHub

* typecheck;
* lint;
* unit test;
* integration test con DB fixture;
* build Next.js;
* build query-engine container.

### 28.2 DB demo cloud

Mantenere almeno:

* Azure SQL AdventureWorksLT;
* MySQL demo equivalente.

Servono per test reali:

* connessione;
* TLS;
* introspection;
* semantic layer;
* query AI;
* grafici;
* verification.

### 28.3 Test critici

Obbligatori:

* SQL validator;
* SQL dialect SQL Server/MySQL;
* chart compiler;
* column formatting;
* tenant isolation;
* permission gates;
* query engine timeout;
* business anchor plausibility;
* total vs breakdown;
* join amplification;
* CTE handling;
* no PII in prompt enrichment default.

---

## 29. Deployment

### 29.1 GCP

Servizi:

* Cloud Run `web`;
* Cloud Run `query-engine`;
* Cloud Run `jobs` opzionale;
* Cloud Scheduler;
* Cloud Tasks;
* Secret Manager;
* Cloud NAT;
* Serverless VPC Connector;
* Cloud VPN dove necessario;
* Cloud Logging;
* Error Reporting;
* Monitoring.

### 29.2 Supabase

* Postgres;
* Auth;
* RLS;
* backups;
* migrations.

### 29.3 GitHub

* repo monorepo;
* GitHub Actions;
* preview deployment;
* protected main branch;
* PR obbligatorie;
* Codex lavora via branch/PR.

---

## 30. Repo structure

```txt
/
├── apps/
│   └── web/
│       ├── app/
│       ├── components/
│       ├── features/
│       ├── lib/
│       └── styles/
│
├── services/
│   └── query-engine/
│       ├── app/
│       │   ├── adapters/
│       │   ├── introspection/
│       │   ├── validation/
│       │   ├── verification/
│       │   ├── profiling/
│       │   └── main.py
│       ├── tests/
│       └── Dockerfile
│
├── packages/
│   ├── db/
│   │   ├── schema/
│   │   └── migrations/
│   ├── contracts/
│   │   ├── query.ts
│   │   ├── chart.ts
│   │   ├── semantic.ts
│   │   └── api.ts
│   ├── chart-compiler/
│   └── shared/
│
├── docs/
│   ├── architecture.md
│   ├── networking.md
│   ├── security.md
│   ├── demo-db.md
│   └── runbooks/
│
├── .github/
│   └── workflows/
│
└── README.md
```

---

## 31. Milestone MVP

### Milestone 1 — Fondamenta

* repo;
* Next.js app;
* Supabase schema;
* auth;
* tenant;
* GCP deploy;
* query-engine skeleton;
* CI.

### Milestone 2 — Connessioni DB

* SQL Server adapter;
* MySQL adapter;
* public allowlist mode;
* TLS;
* Secret Manager;
* test connessione;
* Azure SQL demo;
* MySQL demo.

### Milestone 3 — Snapshot, Queryability Graph, Semantic Layer

* **3A Technical Snapshot V1**: schema scan SQL Server, PK/FK, constraint,
  indici, view definition, lineage, coverage e hash tecnici;
* **3B Queryability Graph V1**: graph tecnico immutabile, cardinalita',
  trust, nullability, self-reference, path fino a quattro hop, ambiguity e
  fanout warning;
* **3C Semantic Layer**: derivazione da graph version, `base_graph_hash`,
  AI enrichment, review admin e activation version.

### Milestone 4 — Query AI

* intent planner;
* clarification flow;
* SQL generation;
* SQL validation;
* execution;
* result table;
* query history.

### Milestone 5 — Chart Compiler

* chart spec;
* ECharts renderer;
* column formatting;
* chart types V1;
* edit chart;
* save widget.

### Milestone 6 — Verification

* total vs breakdown;
* join amplification;
* null/outlier;
* business anchors;
* confidence labels;
* verification drawer.

### Milestone 7 — Dashboard

* dashboard CRUD;
* widget grid;
* widget copy/link;
* refresh;
* cache;
* export.

### Milestone 8 — Pilot hardening

* rate limits;
* cost caps;
* audit;
* error sanitization;
* privacy controls;
* docs;
* demo tenant.

---

## 32. Criteri di successo MVP

Il prodotto è pronto per pilot se:

1. connessione SQL Server via IP allowlist funziona;
2. connessione MySQL via IP allowlist funziona;
3. almeno una VPN pilot è documentata o testata;
4. Queryability Graph viene generato e validato prima del Semantic Layer;
5. semantic layer viene derivato da una graph version e revisionato;
6. “fatturato 2008” su DB demo produce grafico corretto;
7. “prodotti più venduti” produce risultato visibile;
8. query ambigua chiede chiarimento;
9. chart `bar` renderizza sempre se dati compatibili;
10. colonne count non sono formattate come valuta;
11. AI non aggiunge metriche non richieste;
12. Supabase non contiene password DB;
13. SQL validator blocca DDL/DML;
14. risultati non vengono nascosti per skip o engine error;
15. business anchor rileva mismatch grossolani;
16. widget copiato su dashboard non duplica query;
17. audit log traccia azioni sensibili;
18. rate limit e AI cost cap attivi;
19. demo end-to-end ripetibile.

---

## 33. Regole di prodotto non negoziabili

1. Se la domanda è ambigua, chiedere chiarimento.
2. Non indovinare quando il rischio semantico è alto.
3. Non aggiungere colonne non richieste.
4. Non usare AI come validatore di sicurezza.
5. Non usare Supabase come copia del DB cliente.
6. Non mostrare percentuali di confidence come verità scientifica.
7. Non penalizzare privacy finding come errore dati.
8. Non bloccare risultati corretti per controlli non applicabili.
9. Non salvare password DB nel database app.
10. Non costruire verification engine paranoico.
11. Non fare overfitting su AdventureWorksLT.
12. Ogni fix deve essere sistemico, non patch specifica su un dataset.

---

## 34. Esempi comportamento atteso

### 34.1 Domanda chiara

Utente:

> Fatturato 2025 per mese

Sistema:

* usa metrica fatturato verificata;
* usa data default della metrica;
* raggruppa per mese;
* produce bar/line chart;
* fa total vs breakdown;
* confronta business anchor se presente;
* mostra risultato.

### 34.2 Domanda ambigua

Utente:

> Totale documenti 2025

Sistema:

> Per documenti intendi fatture, ordini, DDT, note credito o tutti i documenti commerciali?

Nessuna query prima del chiarimento.

### 34.3 Richiesta grafico specifico

Utente:

> Mostrami il fatturato 2025 come linea

Sistema:

* rispetta line chart se compatibile;
* se non compatibile spiega perché.

### 34.4 Domanda sul grafico

Utente:

> Perché giugno è più alto?

Sistema:

* analizza dati del risultato;
* eventualmente fa drilldown;
* spiega con evidenze;
* non rigenera tutto da zero se non serve.

---

## 35. Prima implementazione Codex

Il primo task da dare a Codex non deve essere “costruisci tutto”.

Primo task corretto:

```txt
Crea monorepo Atlante BI con:
- Next.js app in apps/web
- Supabase schema/migrations in packages/db
- Query engine FastAPI in services/query-engine
- Contracts TypeScript condivisi in packages/contracts
- Dockerfile query-engine
- GitHub Actions con lint/typecheck/test/build
- README architetturale
Non implementare AI, dashboard o grafici. Solo fondazione pulita.
```

Secondo task:

```txt
Implementa db_connections + Secret Manager integration + test connessione SQL Server/MySQL dal query-engine.
```

Terzo task:

```txt
Implementa introspection SQL Server/MySQL e salva schema_snapshot.
```

Solo dopo si passa all’AI.

---

## 36. Nota finale

Questa architettura è più solida perché separa chiaramente:

* UI;
* metadata app;
* query engine;
* AI reasoning;
* deterministic validation;
* chart rendering;
* networking;
* secrets.

Il punto chiave è non far più decidere tutto all’AI in un unico colpo. L’AI deve essere un copilota controllato, non il sistema operativo della BI.
