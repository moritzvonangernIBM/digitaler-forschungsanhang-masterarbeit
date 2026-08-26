# PICOC und Auswahlcodebook

## PICOC

| Element | Operationalisierung |
|---|---|
| Population | LLM-basierte dialogische, toolnutzende oder prozessausführende Agenten |
| Intervention | semantische Ziel-/Evidenz-/Zustandsunterstützung oder deterministische Verifikation, Autorisierung, Policy-, Transaktions- oder Recoverykontrolle zur Laufzeit |
| Comparison | nativer/ungeschützter Agent, deaktivierte Komponente, alternative Laufzeitintervention oder nachvollziehbare Gegenposition |
| Outcome | Aufgaben- oder Zustandskorrektheit, Policy-Adhärenz, Fehler, Regression, Recovery, Stabilität, Kosten oder Latenz |
| Context | mehrstufige Dialog-, Tool-, Workflow- oder Transaktionsausführung; insbesondere Kundenservice, Retail und vergleichbare Geschäftsprozesse |

## Einschluss

Ein Beitrag wird eingeschlossen, wenn alle Basiskriterien und mindestens eine
fachliche Rolle erfüllt sind.

Basiskriterien:

- erste öffentlich prüfbare Fassung mit nachweisbarem Veröffentlichungsdatum
  zwischen dem 1. Januar 2022 und dem 26. Juni 2026;
- Deutsch oder Englisch;
- eigenständiger wissenschaftlicher Beitrag mit nachvollziehbarer Methode;
- fachlich begutachtete Journal- oder Konferenzpublikation als Regelfall;
  aktuelle Preprints werden ausnahmsweise einbezogen, wenn sie unmittelbar
  relevant sind, eine nachvollziehbare Methode und prüfbare Artefakte oder
  Ergebnisse berichten und gegenüber den begutachteten Arbeiten einen
  eigenständigen Erkenntnisbeitrag leisten;
- LLM-basierte agentische Population;
- dialogische, toolbasierte, workflowbezogene oder zustandsverändernde
  Ausführung.

Fachliche Rollen:

- `R1`: empirischer Problem- oder Fehlerbeleg;
- `R2`: semantische Laufzeitunterstützung;
- `R3`: deterministische oder prüfende Laufzeitkontrolle;
- `R4`: passender Benchmark oder Evaluationsansatz;
- `R5`: Korrektur-, Reparatur-, Rollback- oder Recoverymechanismus.

## Ausschluss

- `X1`: außerhalb des festgelegten Suchzeitraums;
- `X2`: keine LLM-agentische Population;
- `X3`: kein Dialog-, Tool-, Workflow-, Zustands- oder Prozessbezug;
- `X4`: kein substanzieller Problem-, Interventions- oder Evaluationsbeitrag;
- `X5`: reine Textgenerierung, RAG oder Chatbotkommunikation ohne
  ausführenden Prozess;
- `X6`: reine Prompt-Injection-, Moderations- oder Outputfilterarbeit ohne
  übertragbare Prozess-/Toolkontrolle;
- `X7`: Editorial, Proceedingsband, Präsentation oder nicht prüfbarer Beitrag;
- `X8`: redundante Publikationsfassung;
- `X9`: Volltext nicht beschaffbar;
- `X10`: Volltext erfüllt die im Abstract erwartete fachliche Rolle nicht.
- `X11`: weder fachlich begutachtete Fassung noch Erfüllung der dokumentierten
  Preprint-Ausnahme nachweisbar.

## Qualitätsbewertung

Volltexte werden getrennt nach Directness und methodischer Qualität bewertet:

- `D1` passende Population;
- `D2` passende Prozess-/Toolausführung;
- `D3` konkreter Mechanismus oder Benchmark;
- `D4` relevante Vergleichsbedingung;
- `D5` relevantes Outcome;
- `Q1` klare Analyseeinheit und Aufgabenpopulation;
- `Q2` rekonstruierbare Systembeschreibung;
- `Q3` faire Vergleichsbedingungen;
- `Q4` nachvollziehbare Ground Truth;
- `Q5` Wiederholungen, Unsicherheit oder offene Artefakte.

Directness bestimmt die Syntheserolle; Qualität und Publikationsstatus
bestimmen das Evidenzgewicht. Zentrale Aussagen werden vorrangig durch
peer-reviewte Beiträge getragen. Preprints werden sichtbar gekennzeichnet,
nicht als alleinige Grundlage zentraler Aussagen verwendet und bei späterer
Publikation auf die begutachtete Fassung aktualisiert.
