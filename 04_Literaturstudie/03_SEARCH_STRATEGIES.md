# Quellenspezifische Suchstrategien

## Gemeinsamer Suchvertrag

Alle Informationsquellen verwenden dieselben zwei Suchfamilien. `F1`
verbindet Agent, Prozessausführung, Anwendungskontext und Evaluation. `F2`
ersetzt den Anwendungskontext durch Begriffe für Laufzeitinterventionen. Die
Publikationsgrenze reicht vom 1. Januar 2022 bis einschließlich 26. Juni 2026.

Die Begriffsblöcke lauten:

- `A` Agent: `large language model agent`, `LLM agent`, `language model agent`,
  `tool-using agent`, `tool using agent`, `conversational agent`;
- `E` Ausführung: `tool call`, `tool use`, `function calling`, `API call`,
  `action execution`, `workflow`, `state machine`, `transaction`, `multi-turn`,
  `task-oriented dialog`, `task-oriented dialogue`;
- `C` Kontext: `customer service`, `customer support`, `retail`, `CRM`,
  `business process`, `transactional`;
- `I` Intervention: `goal tracking`, `intent tracking`, `state tracking`,
  `semantic support`, `input reformulation`, `runtime verification`,
  `guardrail`, `enforcement`, `authorization`, `authorisation`, `policy
  control`, `action control`, `transaction control`, `pre-write`, `recovery`;
- `O` Ergebnis: `evaluation`, `benchmark`, `experiment`, `ablation`,
  `reliability`, `task success`, `task completion`, `final state`, `adherence`,
  `compliance`, `error`, `regression`, `stability`, `cost`, `latency`.

Damit gilt quellenübergreifend `F1 = A AND E AND C AND O` und
`F2 = A AND E AND I AND O`. Phrasen, Pluralformen, Trunkierungen und
Näheoperatoren wurden nur an die Syntax der jeweiligen Quelle angepasst.

## Scopus

Scopus wurde in Titel, Abstract und Schlagwörtern durchsucht. Die beiden
vollständigen Abfragen ergeben sich als:

```text
F1: TITLE-ABS-KEY(A AND E AND C AND O) AND PUBYEAR > 2021 AND PUBYEAR < 2027
F2: TITLE-ABS-KEY(A AND E AND I AND O) AND PUBYEAR > 2021 AND PUBYEAR < 2027
```

Innerhalb von `A` wurde zusätzlich die quellenspezifische Näheform
`((LLM* OR "large language model*") W/3 agent*)` verwendet. Die übrigen
Begriffe wurden als exakte Phrasen oder mit der in den obigen Blöcken
angegebenen Wortstammtrunkierung gesucht.

## ACL Anthology

Die Metadaten der ACL Anthology wurden als lokaler Snapshot nach Publikations-
datum begrenzt. Titel und Abstract wurden kleingeschrieben und je Suchfamilie
auf mindestens einen Treffer aus jedem erforderlichen Begriffsblock geprüft.
Die verwendeten Begriffe entsprechen vollständig den oben dokumentierten
Blöcken; Interpunktionsvarianten wie `multi-turn`/`multi turn` und
`task-oriented`/`task oriented` wurden normalisiert.

## arXiv

arXiv wurde im Feld `all` durchsucht. Die beiden vollständigen Abfragen wurden
aus den oben dokumentierten Phrasen wie folgt zusammengesetzt:

```text
F1: (all:A1 OR ... OR all:An) AND (all:E1 OR ... OR all:En)
    AND (all:C1 OR ... OR all:Cn) AND (all:O1 OR ... OR all:On)
    AND submittedDate:[202201010000 TO 202606262359]
F2: (all:A1 OR ... OR all:An) AND (all:E1 OR ... OR all:En)
    AND (all:I1 OR ... OR all:In) AND (all:O1 OR ... OR all:On)
    AND submittedDate:[202201010000 TO 202606262359]
```

Jeder Platzhalter steht dabei für genau eine Phrase des zugehörigen
Begriffsblocks, beispielsweise `all:"large language model agent"` oder
`all:"runtime verification"`. Bindestriche wurden für die arXiv-Syntax als
Leerzeichen normalisiert.

## IEEE Xplore und ACM Digital Library

IEEE Xplore wurde in `All Metadata`, die ACM Digital Library im Abstractfeld
der ACM Full-Text Collection durchsucht. Die unverändert verwendeten und
quellenspezifisch expandierten F1- und F2-Abfragen liegen unter
`formal/search_audit/search_queries/`. Treffer, Deduplikation und
Screeningentscheidung dokumentiert
`formal/search_audit/ieee_acm_records.csv`.

## Auswahl und Zusammenführung

Treffer beider Familien wurden innerhalb und zwischen den Quellen anhand von
DOI, arXiv-ID und normalisiertem Titel dedupliziert. Anschließend galten für
alle Quellen dieselben Titel-/Abstract-, Volltext- und Evidenzregeln aus
`01_PICOC_AND_CODEBOOK.md` und `02_EVIDENCE_HIERARCHY.md`.
