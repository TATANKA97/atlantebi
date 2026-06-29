# PRD — Atlante BI

## AI-Powered BI Platform per PMI italiane

### Versione 1.1 — Next.js + Supabase + GCP

Aggiornato al 16 giugno 2026. Questo documento sostituisce le assunzioni
manual-first e la generazione SQL libera presenti nelle revisioni precedenti.

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
| Engines V1                    | SQL Server                                                                  |
| Hosting                       | Google Cloud Platform                                                       |
| Auth                          | Supabase Auth oppure Clerk, con preferenza Supabase Auth per ridurre vendor |
| Metadata app                  | Supabase                                                                    |
| Segreti DB cliente            | GCP Secret Manager                                                          |
| AI runtime                    | Provider singolo configurabile, inizialmente Claude/OpenAI production model |
| Sviluppo                      | GitHub + Codex + CI/CD                                                      |
| Grafici                       | ECharts con compiler deterministico                                         |
| Semantic layer                | AI-first, strutturato, versionato e validato deterministicamente            |
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
3. risolve metriche, dimensioni e filtri su artifact semantici validati;
4. compila SQL read-only tramite un Query Compiler deterministico;
5. esegue la query sul DB cliente;
6. verifica il risultato con controlli proporzionati;
7. genera grafico/tabella/KPI;
8. permette di salvare il risultato come widget in dashboard.

Il prodotto non deve sembrare Power BI o Qlik. Deve essere più vicino a Claude, Superpower e Function Health: pulito, editoriale, chiaro, con pochi elementi ma ad alta qualità percepita.

---

## 2. Cosa abbiamo imparato dalla versione precedente

La versione precedente ha mostrato problemi strutturali:

1. L’AI stava decidendo troppe cose insieme: SQL, grafico, formattazione, verifiche, confidence.
   La stessa domanda poteva produrre query e risultati diversi.
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
11. “Fatturato” non era una definizione stabile: poteva usare `SubTotal`,
    `TotalDue` o combinazioni non richieste.
12. Le metriche header potevano essere duplicate da join verso righe detail,
    producendo risultati SQL-validi ma numericamente falsi.
13. PII, sensitivity ed exclusion venivano trattati come un unico concetto.
14. Mancava un controllo indipendente sull’ordine di grandezza del risultato.

La nuova architettura corregge questi punti separando:

* AI interpretation e semantic proposal;
* Semantic Validator deterministico;
* Query Intent Resolver strutturato;
* Query Compiler SQL Server deterministico;
* Result Validator;
* North Star Benchmarks;
* Triangulation Engine.

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

Atlante deve proporre automaticamente una mappa business del DB:

* quali tabelle sono utili;
* quali colonne rappresentano fatturato, clienti, ordini, agenti, scadenze;
* quali metriche strutturate sono candidate;
* quale grain e quali dimensioni sono sicuri per ogni metrica;
* quali ambiguità richiedono chiarimento.

Il Queryability Graph resta l’unica autorità per join, queryability e
sensitivity. L’AI propone significato business, ma non può inventare join,
ampliare l’accesso tecnico o scrivere SQL finale.

Le North Star non sono metriche semantiche. Sono benchmark inseriti
dall’utente per controllare l’ordine di grandezza dei risultati dopo
l’esecuzione.

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
* onboarding manuale obbligatorio del semantic layer;
* SQL finale scritto liberamente dall’AI;
* allocation di metriche header su dimensioni detail;
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
│  - future engine adapters                                  │
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
* North Star benchmark;
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

MySQL è fuori dal perimetro V1 corrente. Il data model può riservare il valore
engine, ma adapter, introspection, compiler e acceptance MySQL verranno
specificati solo dopo il gate SQL Server end-to-end.

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

Requisiti TLS da definire insieme alla futura milestone MySQL.

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
status text -- draft | proposed | active | archived
freshness text -- fresh | stale
builder_version text
ai_model_version text nullable
ai_prompt_version text nullable
validator_version text
policy_version text
revision integer
semantic_hash text
artifact jsonb
validation_report jsonb
created_by uuid
created_at timestamptz
activated_at timestamptz nullable
archived_at timestamptz nullable
rebased_from_version_id uuid nullable
```

La freshness effettiva deriva dal confronto tra `base_graph_hash` e il
`graph_hash` della derivazione corrente. Il campo persistito e' una proiezione
diagnostica, non una seconda fonte di verita'. Una versione active stale resta
disponibile per audit ma non e' utilizzabile dal Query Compiler. L'artifact
canonico usa esclusivamente stable key del Queryability Graph. Active e
archived sono immutabili.

Il dominio semantic legacy viene eliminato nella migration V1. Non esiste un
compatibility layer tra le vecchie proiezioni tecniche `semantic_*` e il nuovo
Semantic Layer. Le FK applicative gia' presenti vengono riallineate al nuovo
registro senza tentare conversioni semantiche dei dati demo.

### 13.8 semantic_layer_tables

```txt
id uuid pk
tenant_id uuid fk
semantic_version_id uuid fk
node_key text
schema_name text
object_name text
object_type text -- table | view
display_name text
description text
included boolean
business_domain text nullable
status text -- system_seeded | ai_proposed | human_verified | rejected | disabled | stale
created_at timestamptz
updated_at timestamptz
```

### 13.9 semantic_layer_columns

```txt
id uuid pk
tenant_id uuid fk
semantic_table_id uuid fk
column_key text
node_key text
physical_name text
display_name text
description text
technical_role text
semantic_role text nullable
included boolean
queryability_status text
inherited_sensitivity text
sensitivity text
format_hint text nullable
status text
created_at timestamptz
updated_at timestamptz
```

Sensitivity e queryability sono ereditarie e monotone: l'arricchimento
semantico puo' restringerle, mai indebolirle.

### 13.10 semantic_layer_relationships

```txt
id uuid pk
tenant_id uuid fk
semantic_version_id uuid fk
edge_key text
from_node_key text
to_node_key text
relationship_shape text -- one_to_one | many_to_one
nullable_fk boolean
self_reference boolean
trusted boolean
verified_by_db boolean
enabled boolean
status text
created_at timestamptz
updated_at timestamptz
```

V1 ammette esclusivamente FK `enabled`, `trusted` e `verified_by_db` del
graph. Il lineage view non e' join evidence.

### 13.11 semantic_layer_business_concepts

```txt
id uuid pk
tenant_id uuid fk
semantic_version_id uuid fk
business_concept_key uuid
canonical_name text
display_name text
description text
synonyms text[]
status text
provenance text -- system | ai | human
created_at timestamptz
updated_at timestamptz
```

I concept raggruppano varianti correlate, non intercambiabili. Per esempio
`revenue` puo' includere `net_header`, `document_total` e `line_detail`.

### 13.12 semantic_layer_metrics

```txt
id uuid pk
tenant_id uuid fk
semantic_version_id uuid fk
metric_key uuid
canonical_name text
metric_definition_hash text
business_concept_key uuid
metric_variant text
source_table_key text
aggregation text -- count | count_distinct | sum | avg | min | max
measure_column_key text nullable
grain_table_key text
grain_column_keys text[]
aggregation_level text
additivity text -- additive | semi_additive | non_additive
default_date_column_key text nullable
required_join_edge_keys text[]
dimension_policy jsonb
common_dimension_compatibility jsonb
preferred_for_grains text[]
preferred_for_dimensions text[]
filters jsonb
format jsonb
value_type text
currency text nullable
synonyms text[]
confidence_score numeric
confidence_label text
compiler_eligibility text
eligibility_reasons text[]
reasoning_summary text
validation_warnings jsonb
status text
provenance text
enabled boolean
created_at timestamptz
updated_at timestamptz
```

`metric_key` e' un'identita' logica opaca e stabile.
`metric_definition_hash` cambia quando cambiano formula, grain, data,
filtri o join.

Ogni metrica dichiara il grain. Una metrica header non puo' essere
raggruppata per dimensioni detail in V1 senza allocation strategy, che e'
fuori scope.

Le dimensioni comuni, le ambiguita' e le esecuzioni AI sono proiettate in
`semantic_layer_metric_common_dimensions`, `semantic_layer_ambiguities` e
`semantic_generation_runs`. Queste tabelle non sostituiscono l'artifact
JSONB canonico: servono per review, audit e interrogazioni operative.

### 13.13 north_star_benchmarks

Benchmark di plausibilità collegabili a una metrica tramite stable key.

```txt
benchmark_key uuid pk
tenant_id uuid fk
connection_id uuid fk
dashboard_id uuid nullable
semantic_version_id uuid nullable
metric_key uuid nullable
name text
description text
expected_value numeric
value_type text
currency text nullable
period_type text
period_start date nullable
period_end date nullable
tolerance_mode text
tolerance_percentage numeric nullable
min_value numeric nullable
max_value numeric nullable
severity text
enabled boolean
created_by uuid
updated_by uuid
created_at timestamptz
updated_at timestamptz
```

Esempio:

```txt
metric_key = <opaque uuid>
canonical_name = fatturato_netto
expected_value = 10000000
currency = EUR
period_type = year
```

La North Star non modifica metrica, `metric_definition_hash`,
`semantic_hash` o queryability. Il Result Validator la usera' dopo
l'esecuzione per controllare l'ordine di grandezza.

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
confidence_label text -- high | medium | low | blocked
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

La coverage lineage distingue:

* object lineage, rappresentata da `view_depends_on`;
* output-column lineage, rappresentata da `view_column_derives_from`.

`view_column_derives_from` viene creato solo quando SQL Server restituisce un
mapping deterministico tra colonna della view e colonna sorgente. Se sono
disponibili solo dipendenze oggetto, la column lineage e' `unavailable`; non
viene inferita analizzando manualmente il testo SQL.

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

La pipeline semantic e' AI-first:

```txt
Queryability Graph
-> deterministic semantic seed
-> AI Semantic Draft
-> Semantic Validator deterministico
-> proposed semantic layer
-> auto-activation o correzione umana
-> active semantic layer
```

La manualita' e' governance e override, non il flusso principale. La
freshness dipende da `base_graph_hash` e `base_policy_hash`, non da
`schema_hash`. Valuta, concept allowlist, preferred variant, stable-key
override, activation policy e soglia minima di metriche eligible partecipano
al policy hash.

### 14.3 Deterministic semantic seed

Il seed importa nodi, colonne e sole FK queryable, enabled e trusted. Eredita
queryability, exclusion, sensitivity e technical role. Non crea significato
business, metriche o join da lineage view.

### 14.4 AI Semantic Draft

L'AI propone naming, descrizioni, sinonimi, domain grouping, semantic role,
format hint, business concept e metriche strutturate. Non genera SQL.

L'input AI e' una proiezione allowlisted del Queryability Graph. Include
stable key, nomi tecnici, tipi, technical role, candidate key espresse con
`column_key`, FK trusted, queryability e sensitivity. Esclude snapshot completo,
view definition,
extended properties, dati raw, sample, credenziali e colonne escluse o
`sensitive`.

Nomi di database, schema, oggetti, colonne e constraint sono dati non fidati:
non possono contenere istruzioni per il modello.

L'output AI contiene solo annotazioni e candidate minimali:

* table e column annotation referenziate tramite stable key;
* concept referenziati tramite `concept_ref` presente nella policy allowlist;
* metriche con concept/variant, source stable key, aggregation, measure stable
  key, default date candidate, format hint e reasoning breve;
* ambiguita' esplicite.

L'AI non assegna e non puo' modificare:

* UUID, hash o versioni artifact;
* queryability, exclusion o sensitivity;
* cardinalita' e relationship tecniche;
* status, provenance, confidence o compiler eligibility;
* grain, join path, dimension safety e validation report.

Il server assegna identity stabile e costruisce la metrica canonica: grain,
shortest trusted grain-safe path, business date, common dimensions, valuta,
definition hash, semantic hash, provenance, confidence ed eligibility. Poi
esegue quality gate e Semantic Validator.

La policy prodotto e' concept-level. Stable-key metric specs sono ammesse solo
per demo/eval o override enterprise. Se una candidate AI non coincide con una
spec, resta auditabile come rejected; il server sintetizza deterministicamente
la metrica mancante con provenance `system/quality_profile`.

Una metrica header non puo' essere spezzata su dimensioni detail in V1.
`SUM(SalesOrderHeader.SubTotal)` per categoria prodotto e' vietata;
`SUM(SalesOrderDetail.LineTotal)` per categoria prodotto e' compatibile.
Allocation strategies sono fuori V1.

### 14.5 Semantic Validator

Il validator controlla stable key, queryability, sensitivity, FK trusted,
tipi, grain, join multiplication, filtri e definition hash. Produce
`blocking_errors`, `warnings` e `info`.

Calcola inoltre confidence e `compiler_eligibility`:

```txt
eligible
eligible_with_disclosure
clarification_required
not_eligible
```

Una proposta AI valida e high-confidence puo' essere usata senza onboarding
manuale, mostrando l'interpretazione applicata.

La confidence certifica la coerenza tecnica rispetto a graph e policy, non la
verita' business. Le candidate AI V1 non contengono filtri. Ambiguita'
`material_ambiguity` aperte si propagano alle metriche coinvolte e richiedono
chiarimento; `minor_ambiguity` e `info` non riducono da sole l'eligibility.

### 14.6 Profiling privacy-safe

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

### 14.7 AI enrichment futuro

L’AI può suggerire:

* display name italiano;
* descrizione business;
* dominio;
* metriche candidate;
* sinonimi business.

L’AI non può suggerire o modificare join tecnici, queryability, exclusion o
sensitivity. Questi campi derivano dal Queryability Graph e dalle policy
server-side.

Una versione `active` è immutabile. Una correzione crea una nuova draft,
la rivalida e, quando attivata, archivia la versione precedente. La review
umana è governance opzionale e gestione delle eccezioni, non un requisito
per iniziare a usare proposte valide ad alta confidenza.

View definitions redatte, sample rows autorizzati e profiling leggero sono
evoluzioni future, non requisiti della foundation V1.

### 14.8 Memorie semantiche

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

## 15. North Star Benchmarks

Le North Star sono valori di riferimento inseriti dall’utente o da un admin
per controllare plausibilità e ordine di grandezza dei risultati.

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

La North Star viene collegata tramite `metric_key` stabile, periodo,
tolleranza e unità. Viene letta dal Result Validator dopo l’esecuzione della
query, quando metrica e periodo sono compatibili.

Non viene inviata di default all’AI Semantic Discovery e non deve influenzare:

* formula o grain della metrica;
* selezione dei join;
* queryability o sensitivity;
* `metric_definition_hash` o `semantic_hash`;
* risultato della query primaria.

Il futuro Intent Resolver può sapere che un benchmark esiste, ma non può
usarlo per alterare il calcolo. L’eventuale triangolazione parte solo dopo
un anomaly flag del Result Validator.

### 15.3 Importante

La North Star non è una metrica e non sostituisce la query. È un controllo
di plausibilità, non una fonte dati primaria e non una validazione semantica.

---

## 16. Query pipeline

### 16.1 Fase 1 — Query Intent Resolver

Input:

* domanda utente;
* Semantic Layer `active`, `fresh` e compiler-eligible;
* memorie rilevanti;
* permessi utente;
* connessione attiva.

Output strutturato:

```json
{
  "status": "ready | needs_clarification",
  "intent": "...",
  "metric_keys": [],
  "dimension_column_keys": [],
  "filters": [
    {
      "column_key": "...",
      "operator": "eq",
      "value": "...",
      "value_type": "string"
    }
  ],
  "time_range": null,
  "requested_chart_type": null,
  "ambiguities": [],
  "interpretations": [],
  "clarifying_question": null,
  "options": []
}
```

L’Intent Resolver seleziona soltanto metriche richieste o strettamente
necessarie alla risposta. Non aggiunge metriche arbitrarie. Può usare una
metrica `ai_proposed` solo quando è valida, fresh e compiler-eligible secondo
la policy. In quel caso deve esporre l’interpretazione applicata.

### 16.2 Ambiguità

Se la domanda è ambigua, il sistema deve chiedere.

Esempio:

> “Mostrami il totale documenti 2024”

Domanda da fare:

> “Per documenti intendi fatture, ordini, DDT, note credito o tutti i documenti commerciali?”

Non deve indovinare.

Esempio specifico:

* “fatturato” usa per default `revenue/net_header` se la domanda è compatibile
  con il grain header;
* “totale documento” usa `revenue/document_total`;
* “fatturato per categoria prodotto” usa `revenue/line_detail`;
* se manca una variante grain-safe, il sistema chiede chiarimento invece di
  compilare un join moltiplicativo.

### 16.3 Fase 2 — Query Plan strutturato

Il resolver produce un piano tipizzato, non SQL:

```txt
selected metrics
dimensions
structured filters
time range
required FK edge paths
grain
ordering
limit
interpretation disclosure
```

Il piano viene rifiutato se:

* la Semantic Layer è stale;
* una metrica è `clarification_required` o `not_eligible`;
* una stable key non esiste;
* una dimensione viola la grain policy;
* il path richiede FK disabled, untrusted o lineage view;
* una colonna è esclusa;
* la sensitivity viola la policy dell’utente.

### 16.4 Fase 3 — Query Compiler deterministico

Il Query Compiler SQL Server trasforma esclusivamente il piano validato in
SQL read-only. Non accetta SQL generato dall’AI e non fa wrapping cieco di
query o CTE.

Responsabilità:

* selezionare tabelle e colonne tramite stable key;
* usare solo `required_join_edge_keys` trusted/enabled;
* rispettare direzione, grain e cardinalità;
* applicare aggregazioni e filtri strutturati;
* impedire header/detail multiplication;
* generare SQL specifico per il dialect SQL Server;
* produrre un manifest compilato per audit e result validation;
* includere soltanto output richiesti.

Regole di sicurezza:

* sqlglot;
* dialect specifico;
* allowlist statement;
* table allowlist;
* column allowlist;
* blacklist difensiva;
* timeout;
* row limit;
* statement singolo.

Il compilatore non può emettere INSERT, UPDATE, DELETE, DDL, EXEC, stored
procedure o riferimenti cross-database.

### 16.5 Fase 4 — Execution read-only

Default:

* timeout 30s;
* row limit 5.000;
* result payload max configurabile;
* read-only DB user;
* connessione pool per tenant/connection;
* retry solo su errori transienti, mai su errori SQL logici.

### 16.6 Fase 5 — Result Validator

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
* North Star plausibility se disponibile e compatibile.

#### Skip onesto

Se un controllo non è applicabile:

```txt
status = skip
```

Non deve penalizzare la confidence.

#### Engine error

Se il verification engine genera una query di controllo non valida:

```txt
status = engine_error
severity = info/warning
```

Non deve essere confuso con dato errato.

Se una North Star segnala uno scostamento rilevante, il Result Validator
produce un anomaly flag. Il futuro Triangulation Engine può eseguire query
diagnostiche controllate; non modifica la metrica né la query primaria.

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
* mancanza baseline storica;
* mancanza North Star.

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

* proporre il Semantic Draft tramite output strutturato;
* interpretare la domanda in metriche, dimensioni, filtri e periodo;
* chiedere chiarimenti;
* spiegare risultato;
* suggerire intent visuali al Chart Compiler;
* arricchire semantic layer;
* creare memorie;
* rispondere a domande sul grafico.

### 22.2 Cosa non deve fare da sola

L’AI non deve essere unica fonte di verità per:

* sicurezza SQL;
* SQL finale;
* selezione o invenzione dei join;
* permessi;
* chart rendering;
* confidence finale;
* formattazione colonne;
* accesso a tabelle;
* queryability, exclusion e sensitivity;
* grain e dimension safety;
* validazione tenant;
* North Star check.

### 22.3 Prompt contract

Ogni fase AI usa un contract JSON dedicato. Non esiste un singolo prompt che
decide insieme semantica, SQL, chart, verification e confidence.

Esempio di output dell’Intent Resolver:

```json
{
  "status": "ready",
  "metric_keys": ["<opaque metric uuid>"],
  "dimension_column_keys": ["<month column key>"],
  "filters": [],
  "time_range": {
    "start": "2025-01-01",
    "end": "2025-12-31"
  },
  "interpretations": [
    "fatturato = revenue/net_header"
  ],
  "ambiguities": []
}
```

Il server valida il payload contro Semantic Layer e Queryability Graph. Il
Query Compiler produce SQL solo dopo questa validazione.

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
* mancanza North Star.

Penalizzare:

* tabella fuori layer;
* colonna inesistente;
* SQL non sicuro;
* risultato vuoto inatteso;
* null/negativi su metrica dove non ammessi;
* join amplification reale;
* North Star mismatch forte;
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
* North Star plausibility;
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
| North Star mismatch      | +2 query diagnostiche   |
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

### Technical Snapshot / Queryability Graph

```txt
POST /api/schema/introspect
GET  /api/queryability/graphs/current
GET  /api/queryability/graphs/:id
POST /api/queryability/rebuild
POST /api/queryability/paths
```

### Semantic Layer

```txt
GET  /api/semantic/current
GET  /api/semantic/versions
GET  /api/semantic/versions/:id
POST /api/semantic/drafts
PATCH /api/semantic/drafts/:id
POST /api/semantic/drafts/:id/generate-ai-draft
POST /api/semantic/drafts/:id/validate
POST /api/semantic/drafts/:id/activate
POST /api/semantic/drafts/:id/rebase
POST /api/semantic/versions/:id/archive
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

### North Star Benchmarks

```txt
GET    /api/north-star-benchmarks
POST   /api/north-star-benchmarks
PATCH  /api/north-star-benchmarks/:id
DELETE /api/north-star-benchmarks/:id
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

Workspace con tab distinti:

* Semantic Layer;
* Technical Snapshot;
* Queryability Graph;
* North Star Benchmarks.

Il tab Semantic Layer mostra proposte già costruite, metriche, concept,
grain, eligibility, confidence, warning e riferimenti tecnici. Le azioni
principali sono conferma, correzione, disable, rigenerazione e rebase. Non è
un editor manuale di tabelle, join e SQL.

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

Mantenere Azure SQL AdventureWorksLT come fixture cloud SQL Server
end-to-end. Una fixture MySQL verrà aggiunta con la relativa milestone.

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
* SQL dialect SQL Server;
* chart compiler;
* column formatting;
* tenant isolation;
* permission gates;
* query engine timeout;
* North Star plausibility;
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

Stato aggiornato al 29 giugno 2026. Le milestone completate restano
documentate perché definiscono le dipendenze delle fasi successive.

### Milestone 1 — Fondamenta e sicurezza di base — completata

* repo;
* Next.js app;
* Supabase schema;
* auth;
* tenant;
* GCP deploy;
* query-engine skeleton;
* CI.

### Milestone 2 — Connessione SQL Server — completata

* SQL Server adapter;
* public allowlist mode;
* TLS;
* Secret Manager;
* test connessione;
* Azure SQL AdventureWorksLT demo.

MySQL è differito. Non deve rallentare il percorso SQL Server end-to-end.

### Milestone 3 — Technical Snapshot SQL Server V1 — completata

* catalog views `sys.*`;
* oggetti, colonne, PK/FK, constraint e indici;
* indexed view;
* view definition e lineage;
* coverage deterministica;
* schema e snapshot hash;
* audit AdventureWorksLT.

### Milestone 4 — Queryability Graph V1 — completata

* graph tecnico immutabile e versionato;
* stable key;
* cardinalità, trust, nullability e self-reference;
* bridge candidate;
* path finding fino a quattro hop;
* ambiguity e fanout warning;
* lineage object e column separato dai join.

### Milestone 5 — Semantic Layer V1 — completata

* **5.1 Foundation pura**: contract, deterministic seed, business concept,
  metric identity/definition hash, grain safety, compact dimension policy,
  compiler eligibility e validator puro;
* **5.2 AI Semantic Discovery**: structured output, prompt/model versioning,
  allowlisted input, identity e safety server-side, eval AdventureWorksLT;
* **5.3 Persistence e lifecycle**: persistenza transazionale, optimistic
  concurrency, freshness, rebase per stable key, activation atomica,
  immutabilità, RLS/RPC e audit;
* **5.4 API e Workspace**: API tenant-scoped e UI AI-first per generazione,
  review, correzione, validation, activation e rebase.
* **5.5 Canonical quality hardening**: AI candidate minimali, policy hash,
  canonical metric builder, synthesis da quality profile, valuta risolta,
  shortest grain-safe path, quality report e messaggi UI coerenti con l'esito.

### Milestone 6 — North Star Foundation — completata

* contract `north_star_benchmarks`;
* persistence tenant-scoped;
* CRUD controllato;
* collegamento tramite `metric_key`;
* tolleranze, periodo, unità e severità;
* tab UI dedicato;
* nessuna triangolazione o modifica del calcolo metrica.

### Milestone 7 — Semantic End-to-End Gate — completata

* graph -> seed -> AI draft -> validation -> activation;
* auto-activation e manual review policy;
* stale e rebase;
* eval AdventureWorksLT;
* verifica DB/API/UI e security suite;
* semantic active pronto come input del compiler;
* v11 AdventureWorksLT considerata baseline valida per procedere:
  active/fresh, quality gate passed, metriche core compiler-eligible,
  ambiguita' aperte ridotte a chiarimenti materiali.
* generazione sincrona mantenuta per il gate; background generation job e UX
  asincrona sono il successivo hardening production.

### Milestone 8 — Query Intent Resolver — completata lato plan-only

* intent strutturato;
* selezione metriche richiesta;
* business concept e metric variant;
* clarification flow;
* disclosure delle interpretazioni;
* nessun SQL libero;
* nessuna esecuzione query;
* nessun Query Compiler in questa milestone.

Stato: implementata come resolver V1 stretto. Una domanda utente diventa un
`QueryIntentPlan` strutturato e validato contro Semantic Layer active/fresh,
Queryability Graph e policy. Il resolver supporta una metrica primaria, al
massimo una dimensione, time range semplice per anno, disclosure e
clarification materialmente necessarie. L'AI e' advisory: il canonicalizer
server-side decide la selezione finale. Il payload non contiene SQL e non
avvia execution.

Acceptance AdventureWorksLT:

* "fatturato 2008" -> `revenue/net_header`, `OrderDate`,
  disclosure status-scope;
* "totale documento 2008" -> `revenue/document_total`, `OrderDate`;
* "quantita' venduta per categoria" -> `quantity_sold/line_quantity`,
  ProductCategory safe;
* "fatturato per categoria prodotto" -> `revenue/line_detail`,
  ProductCategory safe, mai `SubTotal` via detail;
* "clienti" -> `needs_clarification`;
* "clienti che hanno ordinato" -> `customers/order_customers`;
* "clienti in anagrafica" -> `customers/customer_master`;
* "totale documento per categoria prodotto" -> blocked,
  `unsafe_dimension_for_metric`;
* "fatturato e quantita' per categoria" -> blocked,
  `multi_metric_not_supported`;
* Semantic Layer stale, metriche `not_eligible`, filtri/dimensioni sensitive
  o richieste fuori scope devono bloccare il piano con `unsupported_reason`
  strutturato.

### Milestone 9 — Query Compiler SQL Server

* query plan tipizzato;
* compiler deterministico;
* grain e join safety;
* filtri strutturati;
* SQL validation;
* execution read-only;
* result table e query history.

### Milestone 10 — Result Validator e triangolazione controllata

* total vs breakdown;
* join amplification;
* null/outlier;
* North Star anomaly flag;
* triangolazione interna quando necessaria;
* confidence labels;
* verification drawer.

### Milestone 11 — Chart Compiler

* chart spec;
* ECharts renderer;
* column formatting;
* chart types V1;
* edit chart;
* save widget.

### Milestone 12 — Dashboard

* dashboard CRUD;
* widget grid;
* widget copy/link;
* refresh;
* cache;
* export.

### Milestone 13 — Pilot hardening

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
2. almeno una VPN pilot è documentata o testata;
3. Technical Snapshot e Queryability Graph precedono sempre il Semantic Layer;
4. Semantic Layer deriva da una graph version tramite stable key;
5. una versione active è fresh, validata e immutabile;
6. una versione stale non è compilabile;
7. “fatturato 2008” viene risolto senza configurazione manuale;
8. “fatturato per categoria prodotto” usa una metrica detail grain-safe;
9. una query ambigua chiede chiarimento;
10. l’AI non genera SQL finale e non inventa join;
11. il Query Compiler emette solo SQL Server read-only validato;
12. l’AI non aggiunge metriche o colonne non richieste;
13. una North Star rileva mismatch grossolani senza cambiare la metrica;
14. chart `bar` renderizza sempre se i dati sono compatibili;
15. colonne count non sono formattate come valuta;
16. Supabase non contiene password DB;
17. risultati non vengono nascosti per skip o engine error;
18. widget copiato su dashboard non duplica query;
19. audit log traccia azioni sensibili;
20. rate limit e AI cost cap sono attivi;
21. demo SQL Server end-to-end è ripetibile.

---

## 33. Regole di prodotto non negoziabili

1. Se la domanda è ambigua, chiedere chiarimento.
2. Non indovinare quando il rischio semantico è alto.
3. Non aggiungere colonne non richieste.
4. Non usare AI come validatore di sicurezza.
5. Non permettere all’AI di scrivere SQL finale o inventare join.
6. Non usare Semantic Layer stale nel Query Compiler.
7. Non usare Supabase come copia del DB cliente.
8. Non mostrare percentuali di confidence come verità scientifica.
9. Non penalizzare privacy finding come errore dati.
10. Non bloccare risultati corretti per controlli non applicabili.
11. Non salvare password DB nel database app.
12. Non costruire verification engine paranoico.
13. Non fare overfitting su AdventureWorksLT.
14. Non confondere North Star e metriche semantiche.
15. Ogni fix deve essere sistemico, non patch specifica su un dataset.

---

## 34. Esempi comportamento atteso

### 34.1 Domanda chiara

Utente:

> Fatturato 2025 per mese

Sistema:

* usa metrica fatturato verificata;
* usa data default della metrica;
* raggruppa per mese;
* il Query Compiler genera SQL dal piano strutturato;
* produce bar/line chart;
* fa total vs breakdown;
* confronta la North Star se presente;
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

## 35. Prossima implementazione

Fondamenta, connessione SQL Server, Technical Snapshot, Queryability Graph,
North Star Foundation e Semantic Layer fino al Semantic End-to-End Gate sono
completati. La v11 AdventureWorksLT e' la baseline di partenza per la query
pipeline: semantic active/fresh, quality gate passed, metriche core
compiler-eligible e ambiguita' aperte limitate a chiarimenti materiali.

La Milestone 8 - Query Intent Resolver e' implementata come gate plan-only.
Il resolver:

* legge domanda utente, Semantic Layer active/fresh, policy utente e graph;
* seleziona solo metriche richieste o strettamente necessarie;
* sceglie metric variant coerenti con grain e dimensioni;
* produce un Query Plan strutturato, non SQL;
* blocca Semantic Layer stale, metriche non eligible e join/fanout unsafe;
* chiede chiarimento quando l'intento resta materialmente ambiguo;
* restituisce disclosure quando usa metriche AI-proposed o policy-resolved;
* espone un endpoint query-engine `POST /query/intent/resolve` e una pagina
  debug web `/query-intent`.

Fuori scope Milestone 8:

* Query Compiler SQL Server;
* esecuzione query;
* chart/dashboard;
* Result Validator;
* triangolazione;
* generazione semantica asincrona production.

La generazione semantica asincrona resta hardening production successivo, ma
non deve bloccare il percorso MVP. Prima serve sapere interpretare una domanda
in un piano sicuro; questo gate ora esiste. Il prossimo passo MVP e' compilare
quel piano in SQL Server deterministico.

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
