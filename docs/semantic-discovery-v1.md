# Semantic Discovery V1

## Scope

La Milestone 2 del piano Semantic Layer V1, tracciata nel PRD globale come
`3C.2 AI Semantic Discovery`, trasforma il seed deterministico in una proposta
semantica strutturata. Non include persistenza, activation, API o UI.

```text
Queryability Graph
-> allowlisted discovery input
-> structured AI proposal
-> deterministic server compilation
-> Semantic Validator
-> proposed Semantic Layer
```

L'AI propone. Il server mantiene ogni decisione tecnica o autoritativa.

## Confine dati

L'input `semantic_discovery_input.v1` contiene esclusivamente:

- stable key di nodi, colonne e FK trusted;
- nomi tecnici, tipi, technical role e nullability;
- candidate key espresse esclusivamente tramite `column_key`;
- queryability e sensitivity;
- bridge trait e stato lineage della view.

Non contiene:

- snapshot tecnico completo;
- view definition o extended properties;
- dati, sample row o valori distinti;
- credenziali;
- colonne escluse o classificate `sensitive`;
- edge di lineage come join.

I nomi tecnici sono input non fidato. Il system prompt vieta di interpretare
testo nei nomi come istruzioni.

## Output AI

`semantic_ai_draft.v1` consente:

- annotazioni table/column;
- business concept con `concept_ref`;
- metriche strutturate;
- ambiguita' e domande di chiarimento.

Non consente UUID, hash, raw SQL, queryability, sensitivity, status,
provenance, confidence, eligibility, dimension safety o validation report.
Campi extra causano il rifiuto del payload.

## Compilazione server

Il compiler:

1. verifica ogni stable key contro l'input allowlisted;
2. applica solo campi semanticamente annotabili sul seed;
3. assegna UUIDv5 stabili per connection, concept e metric variant;
4. preserva queryability, sensitivity e relationship dal graph;
5. calcola dimension safety dai path FK;
6. calcola metric definition hash e semantic hash;
7. assegna `status=ai_proposed` e `provenance=ai`;
8. invoca il Semantic Validator, che calcola confidence ed eligibility.

Una proposta con stable key inventate, edge non trusted, colonne escluse,
duplicati o path non valido viene rifiutata.

Le ambiguita' AI usano `target_ref` secondo il tipo:

- `table` e `column`: stable key del graph;
- `business_concept`: `concept_ref` della proposta;
- `metric`: `canonical_name` della proposta.

Il server risolve i riferimenti logici in UUID stabili e rifiuta target
inesistenti. La confidence risultante misura la validita' tecnica della
proposta rispetto al graph e alle policy; non certifica da sola la correttezza
del significato business.

In assenza di profiling dati, un filtro letterale proposto dall'AI puo' essere
validato per tipo e struttura ma non per esistenza o significato del valore.
Queste metriche ricevono `clarification_required` con warning
`AI_FILTER_VALUE_UNVERIFIED`. Le ambiguita' aperte su table o column vengono
propagate a tutte le metriche che referenziano quel target.

Gli UUIDv5 sono stabili a parita' di connection e riferimenti logici. Il
carry-forward di identita' dopo rename o rebase appartiene alla persistenza e
al lifecycle della Milestone 3.

## Provider

L'adapter OpenAI usa Responses API con Structured Outputs Pydantic:

- model default: `gpt-5.5`, configurabile dal chiamante;
- prompt version: `semantic-discovery.v1`;
- reasoning effort: `medium`;
- verbosity: `low`;
- input canonico massimo: 2 MB;
- output massimo: 20.000 token;
- timeout request: 120 secondi;
- `store=false`.

La logica applicativa dipende da un gateway iniettato. Test e CI usano un
gateway fake e non richiedono rete o API key.

Se l'input supera il limite V1, la discovery fallisce esplicitamente. Il
partizionamento per domain e la riconciliazione multi-run restano fuori da
questa milestone; non viene effettuato truncation silenzioso.

## Provenance

Ogni generazione restituisce:

- provider;
- model version;
- prompt version;
- timestamp;
- hash dell'input allowlisted;
- hash della proposta;
- response id.

Il contenuto completo del prompt o della proposta non deve essere loggato in
chiaro.

## Eval gate

Le eval AdventureWorksLT sono deterministiche e offline. Il gate richiede:

- 13 nodi, 124 colonne AI-visible e 12 FK trusted nell'input;
- zero riferimenti a PasswordHash, PasswordSalt o CreditCardApprovalCode;
- varianti revenue `net_header`, `document_total` e `line_detail`;
- metriche quantity, orders e customer populations;
- header revenue per ProductCategory `forbidden`;
- line revenue per ProductCategory `safe`;
- stable key tutte valide;
- identity server-side stabile a parita' di proposta;
- campi autoritativi AI rifiutati;
- proposta compilata validata senza blocking error.

Safety, privacy e reference integrity sono gate binari: non possono essere
compensati da un punteggio medio.
