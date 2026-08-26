# Digitaler Forschungsanhang

Dieser Ordner ergänzt die Masterarbeit **„Gestaltung und faktorielle
Evaluation modularer Laufzeitinterventionen für transaktionale LLM-Agenten im
Kundenservice“** von Moritz von Angern.

Der Anhang enthält den thesis-relevanten Implementierungskern, die
vollständigen Trajektorien der finalen Sechs-Seed-Matrix, aggregierte
Evaluationsergebnisse und die Dokumentation der Literaturstudie. Der Einstieg
erfolgt über diese Datei und den Dateikompass in `MANIFEST.md`.

## Inhalt

| Ordner | Inhalt |
|---|---|
| `01_Code/` | Kuratierter Implementierungskern der Laufzeitinterventionen und zugehörige Tests. |
| `02_Evaluation/` | Aggregierte Ergebnisse, Seedanalyse und Mechanismenauswertung. |
| `03_Trajektorien/` | Alle 1.920 Dialogtrajektorien und alle 1.920 zugehörigen Mechanismustraces. |
| `04_Literaturstudie/` | Reviewprotokoll, Suchstrategien, Auswahl- und Synthesetabellen. |
| `05_Dokumentation/` | Systemabbildungen, Metrikdefinitionen und technische Orientierung. |
| `06_Thesis/` | Finale Fassung der Masterarbeit. |

## Experimentmatrix

Die finale Evaluation umfasst 80 Aufgaben, sechs gepaarte Seeds und vier
Bedingungen. Daraus ergeben sich 1.920 Task-Seed-Bedingungs-Zellen.

| Bedingung | Semantische Unterstützung A | Pre-Write-Kontrolle B |
|---|---:|---:|
| `C0_NATIVE` | aus | aus |
| `C1_SEMANTIC_SUPPORT` | an | aus |
| `C2_PREWRITE_CONTROL` | aus | an |
| `C3_COMBINED_INTERVENTION` | an | an |

## Datenumfang und Bereinigung

Der Trajektorienbestand ist hinsichtlich der final ausgewerteten Zellen
vollständig. Entfernt wurden ausschließlich technisch irrelevante
Provider-Rohdaten, verschlüsselte interne Reasoning-Felder, Sitzungskennungen,
lokale Dateipfade und exakte Zeitstempel. Dialoge, Toolaufrufe, Kosten,
Laufzeiten, Zustandswirkungen und Mechanismusereignisse bleiben erhalten.

Der Ordner enthält keine Zugangsdaten, Entwicklungsnotizen, Versionshistorie,
IDE-Dateien oder internen Bearbeitungsprotokolle. Publikationsvolltexte sind
aus urheberrechtlichen Gründen nicht enthalten.

## Technische Prüfung

Der Code-Kern wurde mit Python 3.12 geprüft. Im Ordner `01_Code/` kann der
Nachweistest mit folgendem Befehl ausgeführt werden:

```bash
python -m pytest -q
```

