# Implementierungskern

Dieser Ordner enthält nur den unmittelbar thesis-relevanten Code. Die drei
Artefaktebenen gehören zu demselben Laufzeitsystem und sind keine alternativen
Implementierungen.

## Struktur

| Ordner | Zweck |
|---|---|
| `artifact/shared/` | Gemeinsame Laufzeitlogik mit Verträgen, Orchestrator, Telemetrie und sichtbarem Prozesszustand. |
| `artifact/retail/` | Retail-spezifische Anbindung mit Zustandsprojektion, Toolbindungen und Retail-Regeln. |
| `artifact/factorial/` | Finale 2×2-Studienlogik für C0 bis C3. Hier liegen A und B für die Evaluation. |
| `evaluation/` | Offline-Bewertung der finalen Zustandswirkung. |
| `tests/` | Kleine Nachweistests fuer A, B, Orchestrierung und Evaluation. |
| `config/` | Finale Design-Konfiguration für C0 bis C3. |

## Lesereihenfolge

1. `artifact/factorial/semantic_support.py` für A.
2. `artifact/factorial/prewrite_validation.py` für B.
3. `artifact/factorial/tau2_adapter.py` für die Bedingungen C0 bis C3.
4. `evaluation/offline/transactional_effect_oracle.py` für die Ergebnisbewertung.

Die Ordner sind keine alternativen Systeme, sondern Ebenen desselben Artefakts:
gemeinsame Laufzeitlogik, Retail-Anbindung, faktorielle Studienlogik und
getrennte Offline-Evaluation.

## Technische Prüfung

Vom Ordner `code_core/` aus lässt sich der kompakte Nachweistest ausführen mit:

```bash
python -m pytest -q
```

Die Tests prüfen Faktortrennung, semantische Unterstützung, Pre-Write-Kontrolle,
Orchestrierung und Offline-Evaluation.
