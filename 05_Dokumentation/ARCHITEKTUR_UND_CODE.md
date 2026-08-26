# Architektur und Codezuordnung

Das Artefakt ist eine Laufzeitinterventionsschicht um einen nativen
LLM-Agenten. Es besteht nicht aus mehreren kooperierenden Agenten. Die zwei
Faktoren greifen an unterschiedlichen Stellen desselben Ausführungspfads ein.

## Systemkomponenten

1. Die Experimentsteuerung legt Task, Seed, Bedingung, Policy und initialen
   Datenbankzustand fest.
2. Der User-Simulator erzeugt die synthetischen Nutzeräußerungen.
3. Der Laufzeit-Orchestrator aktualisiert den sichtbaren Prozesszustand und
   aktiviert abhängig von der Bedingung A und B.
4. Die Retail-Umgebung stellt Tools und Datenbank bereit.
5. Die Offline-Evaluation vergleicht Grundwahrheit, Episodenrecord und finalen
   Datenbankzustand.

Die Gesamtstruktur zeigt `Systemoekosystem.png`. Der konkrete Eingriffspfad von
A und B ist in `Interventionsablauf.png` dargestellt.

## Zuordnung zum Code

| Konzept | Codebereich | Aufgabe |
|---|---|---|
| Gemeinsame Laufzeit | `01_Code/artifact/shared/` | Verträge, Orchestrierung, sichtbarer Zustand und Telemetrie |
| Retail-Anbindung | `01_Code/artifact/retail/` | Zustandsprojektion, Toolbindung und domänenspezifische Regeln |
| Faktor A | `01_Code/artifact/factorial/semantic_support.py` | Quellengebundene Ziel- und Evidenzfortschreibung sowie Unterstützungskarte |
| Faktor B | `01_Code/artifact/factorial/prewrite_validation.py` | Deterministische Prüfung eines mutierenden Schreibkandidaten |
| Faktorieller Pfad | `01_Code/artifact/factorial/tau2_adapter.py` | Aktivierung von C0 bis C3 im gemeinsamen Laufzeitpfad |
| Offlinebewertung | `01_Code/evaluation/offline/` | Vergleich erwarteter und beobachteter Zustandswirkungen |
| Experimentdesign | `01_Code/config/final_design.json` | Seeds, Bedingungen, Modelle und Eingriffsgrenzen |

Die drei Artefaktordner sind keine konkurrierenden Implementierungen. `shared`
stellt die domänenunabhängige Basis bereit, `retail` bindet diese Basis an die
Benchmarkdomäne und `factorial` implementiert die im Experiment aktivierten
Faktoren A und B.

