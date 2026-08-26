# Vollständiger Trajektorienbestand

Dieser Ordner enthält alle final ausgewerteten Episoden der Sechs-Seed-Matrix.
Jede Task-Seed-Bedingungs-Zelle besitzt genau eine Dialogtrajektorie und genau
einen Mechanismustrace.

## Struktur

```text
dialog_trajectories/
  seed_<Seed>/
    <Bedingung>/
      task_<Task-ID>.json

mechanism_traces/
  seed_<Seed>/
    <Bedingung>/
      task_<Task-ID>.json
```

`trajectory_index.csv` verbindet beide Dateien mit der jeweiligen Bedingung,
Task-ID, den Endpunkten, Ressourcenwerten und SHA-256-Prüfsummen. Die Datei
`trajectory_summary.json` dokumentiert den Umfang des Bestands.

## Inhalt der Dialogtrajektorien

Die Dialogtrajektorien enthalten die sichtbare Kommunikation, Toolaufrufe und
Toolresultate, Token- und Kostenangaben, Laufzeit, Abbruchgrund und beobachtete
Zustandswirkungen. Die enthaltenen Kundendaten sind synthetische Daten der
Benchmarkumgebung.

## Inhalt der Mechanismustraces

Die Mechanismustraces protokollieren die Eingriffsgelegenheiten, Entscheidungen
und Folgewirkungen von A und B. Dazu gehören unter anderem AOP-, G-, AC-, BOP-
und B-Kennungen sowie die fortlaufende Ereignisposition.

## Technische Bereinigung

Providerinterne Rohantworten, verschlüsselte Reasoning-Inhalte,
Sitzungskennungen, lokale Pfade und exakte Zeitstempel wurden nicht in den
Abgabeanhang übernommen. Diese Felder sind weder für die Rekonstruktion des
Dialogs noch für die Prüfung der Zustandswirkung erforderlich. Fachliche
Nachrichten, Toolaktionen und Mechanismusereignisse wurden nicht gekürzt.

