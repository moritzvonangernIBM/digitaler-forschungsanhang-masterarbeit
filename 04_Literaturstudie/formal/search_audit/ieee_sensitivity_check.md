# Sensitivitaetspruefung der IEEE-Xplore-Suche

## Zweck

Die beiden regulaeren IEEE-Suchfamilien F1 und F2 ergaben in `All Metadata`
keine Treffer. Eine Kontrollabfrage zu `"conversational agent"` belegte, dass
der Datenbankzugriff und die Suchfunktion technisch arbeiteten. Um zusaetzlich
zu pruefen, ob die Nullmenge allein aus der Schnittmenge der Suchbloecke
entstand, wurden zwei gelockerte Sensitivitaetsabfragen ausgefuehrt. Sie dienen
der Recall-Pruefung und ersetzen weder die vorab festgelegten Hauptabfragen
noch deren Auswahlregeln.

## Abfragen und Ergebnisse

1. Agent, Ausfuehrung und Ergebnisbezug ohne Kontext- beziehungsweise
   Interventionsblock: 53 Treffer.
2. Agent, Ausfuehrung und Kontext- beziehungsweise Interventionsbezug ohne
   Ergebnisblock: 5 Treffer.

Die exakten IEEE-Command-Search-Ausdruecke sind in
`search_queries/ieee_sensitivity_without_context.txt` und
`search_queries/ieee_sensitivity_without_outcome.txt` archiviert. Fuer die
fachliche Pruefung galten unveraendert die Publikationsgrenze vom 1. Januar
2022 bis einschliesslich 26. Juni 2026 sowie die dokumentierten Ein- und
Ausschlussregeln.

## Fachliche Pruefung

Die Titelsichtung der 53 beziehungsweise 5 Treffer zeigte drei Gruppen:

- Bereits ueber Scopus oder arXiv identifizierte Arbeiten, darunter Beitraege
  zu Robustheit unter Schema-, Policy- und Toolset-Drift, Runtime Verification
  und Workflow-Provenienz.
- Arbeiten ausserhalb des fokalen transaktionalen Prozesskontexts, etwa zu
  Visual Analytics, Schaltungsentwurf, Telekommunikation, Medizin oder
  Softwareentwicklung.
- Methodisch oder inhaltlich indirekte Arbeiten. Dazu gehoeren eine
  konzeptionelle Taxonomie mehrschichtiger Guardrails ohne eigene
  Wirkungsevaluation, eine Studie zu Bugs in Orchestrierungsframeworks und
  eine statische Defekterkennung fuer Agentencode. Diese Arbeiten untersuchen
  weder die isolierte Wirkung semantischer Unterstuetzung noch die Wirkung
  einer deterministischen Pre-Write-Kontrolle auf transaktionale Endzustaende.

Die Sensitivitaetspruefung ergab damit keine neue, nach den festgelegten Regeln
in die konzeptzentrierte Synthese aufzunehmende Kernstudie. Die PRISMA-Zahlen
und der Korpus von 25 Studien bleiben unveraendert. Das Ergebnis stuetzt die
Interpretation, dass die Nulltreffer der regulaeren IEEE-Abfragen aus deren
enger, auf den unmittelbaren Reviewfokus gerichteter Blockschnittmenge folgen
und nicht aus einem technischen Ausfall der Datenbank.
