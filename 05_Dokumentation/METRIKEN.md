# Metriken und Auswertungseinheit

## Auswertungseinheit

Die elementare Auswertungseinheit ist eine Task-Seed-Bedingungs-Zelle. Alle
vier Bedingungen verwenden dieselben Aufgaben und Seeds. Die Bedingungen
werden deshalb innerhalb identischer Task-Seed-Paare verglichen.

## Primärer Endpunkt

**DB Match** zeigt, ob der finale Datenbankzustand der für die Aufgabe
definierten Grundwahrheit entspricht. Die Metrik wird auf allen 80 Aufgaben
ausgewertet.

## Strenger sekundärer Endpunkt

**Exact Mutation** zeigt bei schreibpositiven Aufgaben, ob die beobachteten
Geschäftszustandsänderungen exakt den erwarteten Änderungen entsprechen. Eine
fehlende, zusätzliche oder falsch parametrisierte Mutation führt zu einem
negativen Ergebnis.

## Ergebniswechsel

**Saved** bezeichnet eine Zelle, in der C0 den Endpunkt verfehlt und die
Interventionsbedingung ihn erreicht. **Broken** bezeichnet den umgekehrten
Wechsel. **Unchanged** umfasst stabile Erfolge und stabile Misserfolge.

## Wiederholungsstabilität

Seedweise Mittelwerte und Standardabweichungen zeigen Lage und Streuung der
Erfolgsraten. `pass@k` beschreibt, ob eine Aufgabe in mindestens einer von k
Ausführungen gelöst wird. `pass^k` beschreibt, ob sie in allen k Ausführungen
gelöst wird.

## Ressourcen

Der Ressourcenvergleich umfasst Agenten-API-Kosten, technische Laufzeit,
Toolaufrufe und Nachrichten. Nutzer-Simulator-Kosten werden getrennt
ausgewiesen und nicht als Artefaktaufwand interpretiert.

