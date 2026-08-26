# Sichtbare Dokumentation der Literatur-Synthese

Dieser Anhang dokumentiert die Synthese bewusst tabellarisch, damit die
Auswahlentscheidungen prüfbar bleiben und nicht als freier Notizzettel neben der
Thesis stehen.

## 1. Paper-Ebene

Die Datei `formal/evidence_tables/final_study_matrix.csv` ist der zentrale
Studienkorpus. Pro Paper sind dort Studien-ID, BibTeX-Schlüssel, Titel,
Identifikationsweg, Quellenstatus, analytische Rolle, Einschlussbegründung und
zulässige Evidenzverwendung festgehalten.

Die Spalte `synthesis_roles` zeigt, wofür ein Paper in der Synthese verwendet
wurde. Die Spalte `inclusion_rationale` enthält die kurze inhaltliche Notiz,
warum die Studie für die Reviewfrage relevant ist.

Die Datei `formal/evidence_tables/study_extraction_notes.csv` ergänzt diese
formale Matrix um die eigentlichen Arbeitsnotizen zu allen 25 Studien. Die
Einträge halten knapp fest, worum es in der Arbeit geht, welche Mess- oder
Untersuchungslogik verwendet wird, welcher Punkt für die Synthese relevant ist,
wo die Aussage begrenzt werden muss und an welcher Fundstelle dies geprüft
wurde. Die Formulierungen sind bewusst stichpunktnah und keine nachträglich
verfassten Paper-Abstracts.

## 2. Qualitäts- und Evidenzebene

Die Datei `formal/evidence_tables/quality_appraisal.csv` dokumentiert für jede
aufgenommene Studie die Qualitätsprüfung. Bewertet werden unter anderem klare
Untersuchungseinheit, rekonstruierbares System, Vergleichslogik, transparente
Outcome- oder Ground-Truth-Basis sowie Wiederholbarkeit beziehungsweise offenes
Artefakt.

Die Spalte `appraisal_use` begrenzt, ob eine Studie zentrale Aussagen tragen
darf oder nur ergänzend für frontier-nahe Einordnung verwendet wird.

## 3. Synthese- und Argumentationsebene

Die Datei `formal/evidence_tables/claim_evidence_matrix.csv` verbindet die
zentralen Syntheseaussagen mit den jeweils tragenden Studien. Sie trennt
primäre Evidenz, unterstützende Evidenz, frontier-nahe Ergänzung und Grenzen der
Aussage.

Damit ist sichtbar, welche Paper welche Aussage in Kapitel 3 stützen und wo die
Aussage bewusst begrenzt wird.

## 4. PRISMA- und Prozesszahlen

Die Datei `formal/evidence_tables/prisma_counts.json` enthält die finalen
Zahlen des Auswahlprozesses. Die methodische Rahmung steht in
`00_START_HERE_FINAL.md`, `00_PROTOCOL_FREEZE.md`,
`01_PICOC_AND_CODEBOOK.md` und `02_EVIDENCE_HIERARCHY.md`.

## 5. Beitrag der ACM-DL-Suche

Die Suche in der ACM Digital Library identifizierte `fastWorkflow` als
peer-reviewten Synthesebeitrag. Die Studie trägt zu R1, R2 und R4 bei: Sie
klassifiziert Fehler in conversational Workflows, prüft eine modularisierte
semantische Laufzeitarchitektur mit Ablationen und berichtet drei unabhängige
Durchläufe, Stabilität, Kosten sowie offene Traces. Der Beitrag schärft die
Gegenabgrenzung, weil semantische Teilkomponenten bereits kontrolliert
ablierbar sind, enthält aber keine separat aktivierbare deterministische
Pre-Write-Kontrolle.
