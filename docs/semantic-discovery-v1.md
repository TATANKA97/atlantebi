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
- candidate metriche minimali con soli stable key allowlisted;
- ambiguita' e domande di chiarimento.

Non consente UUID, hash, raw SQL, queryability, sensitivity, status,
provenance, confidence, eligibility, dimension safety o validation report.
Campi extra causano il rifiuto del payload.

## Compilazione server

Il canonical builder:

1. verifica ogni stable key contro l'input allowlisted;
2. applica solo campi semanticamente annotabili sul seed;
3. assegna UUIDv5 stabili per connection, concept e metric variant;
4. preserva queryability, sensitivity e relationship dal graph;
5. deriva grain, shortest trusted grain-safe path, business date e dimensioni;
6. applica la valuta dalla policy, senza accettarla dall'AI;
7. confronta stable-key quality specs e sintetizza metriche required mancanti;
8. calcola metric definition hash e semantic hash;
9. assegna provenance auditabile;
10. invoca quality gate e Semantic Validator.

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

Filtri AI, raw SQL, grain e join path dichiarati dal modello sono fuori dal
candidate contract. Le ambiguita' materiali vengono propagate alle metriche
che referenziano il target; minor ambiguity e info restano diagnostiche.

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

L'adapter Anthropic usa Messages API con Structured Outputs Pydantic e
adaptive thinking. Il contratto canonico completo supera il limite interno di
compilazione della grammatica Anthropic, quindi l'adapter esegue due fasi
sequenziali:

1. annotazioni di tabelle e colonne con business concept;
2. metriche e ambiguita', usando anche i concept proposti nella prima fase.

Le due risposte vengono ricomposte e validate come un unico
`semantic_ai_draft.v1`. I response id di entrambe le chiamate sono conservati
nella provenance. Questa suddivisione e' specifica del transport Anthropic e
non modifica compiler, validator o contratto persistito.

La fase annotazioni e' intenzionalmente sparsa e privilegia gli oggetti
business-relevant. Gli oggetti non annotati restano nel seed deterministico;
non vengono rimossi dal Semantic Layer. Entrambe le fasi usano lo streaming
Messages API per mantenere attive le richieste lunghe. L'adapter disabilita i
retry SDK automatici e applica un timeout esplicito per fase, evitando latenze
nascoste oltre il timeout end-to-end.

La fase annotazioni usa effort basso e un budget di 8k token; la fase metriche
mantiene l'effort scelto dal tenant con un budget di 12k. Ogni fase ha una
deadline reale di 240 secondi e l'intera generazione una deadline di 450
secondi, inferiore al timeout Cloud Run. I massimi sincroni del provider non
sono usati come budget applicativo: su un endpoint interattivo consentirebbero
thinking eccessivamente lungo, costi imprevedibili e timeout infrastrutturali.

Anche l'output metriche e' bounded: massimo 10 metriche, con liste annidate
brevi per dimensioni, filtri, grain preferiti e sinonimi. Il contratto
canonico resta piu' ampio; questi limiti riguardano soltanto una singola
generazione Anthropic e impediscono output esaustivi che verrebbero troncati.
Nel transport Anthropic le ambiguita' sono annidate nel business concept o
nella metrica a cui appartengono. Il server assegna il `target_ref` durante la
conversione al contratto canonico: il modello non puo' inventare un target e
l'incertezza non viene eliminata silenziosamente.

Il transport metriche Anthropic e' intenzionalmente piu' piccolo del contratto
canonico. Il modello propone concept/variant, identita', sorgente,
aggregazione, measure, data candidate, formato e motivazione. Grain, join,
compatibilita' dimensionali, valuta, additivita', confidence ed eligibility
vengono derivati dal server e restano soggetti a quality gate e validator.

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
