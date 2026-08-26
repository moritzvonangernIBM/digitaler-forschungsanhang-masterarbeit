# Finale Sechs-Seed-Auswertung der Retail-Matrix

## Datenbasis und Abgrenzung

Die finale Matrix umfasst 80 Aufgaben, sechs gepaarte Seeds und vier
Bedingungen, insgesamt 1.920 vollständige Zellen. Für Exact Mutation
bilden die 72 Aufgaben mit erwarteter Schreibaktion die festgelegte
Auswertungspopulation (432 Zellen je Bedingung). Die ausgewählten 1.920
Job-IDs stimmen exakt mit den sechs finalen Evaluationsmatrizen überein.

## Aggregierte Endpunkte

| Bedingung | DB Match | Exact Mutation | Agentenkosten/Zelle | Laufzeit/Zelle |
|---|---:|---:|---:|---:|
| C0 Native | 342/480 = 71,3 % | 293/432 = 67,8 % | 0,0069 USD | 45,2 s |
| C1 Semantik | 371/480 = 77,3 % | 320/432 = 74,1 % | 0,0100 USD | 57,1 s |
| C2 Kontrolle | 350/480 = 72,9 % | 305/432 = 70,6 % | 0,0069 USD | 45,2 s |
| C3 Kombination | 367/480 = 76,5 % | 317/432 = 73,4 % | 0,0100 USD | 57,7 s |

Direkt gegenüber C0 entspricht dies für C1 +6,0 Prozentpunkten DB Match und
+6,3 Punkten Exact Mutation, für C2 +1,7 beziehungsweise +2,8 Punkten und für
C3 +5,2 beziehungsweise +5,6 Punkten.

## Verteilung über die Seeds

| Seed | C0 DB | C1 DB | C2 DB | C3 DB |
|---|---:|---:|---:|---:|
| 976301 | 70,0 % | 78,8 % | 71,3 % | 80,0 % |
| 976302 | 72,5 % | 81,3 % | 73,8 % | 75,0 % |
| 976303 | 72,5 % | 75,0 % | 78,8 % | 76,3 % |
| 976304 | 70,0 % | 81,3 % | 73,8 % | 76,3 % |
| 976305 | 67,5 % | 78,8 % | 71,3 % | 76,3 % |
| 976306 | 75,0 % | 68,8 % | 68,8 % | 75,0 % |

| Seed | C0 Exact | C1 Exact | C2 Exact | C3 Exact |
|---|---:|---:|---:|---:|
| 976301 | 65,3 % | 75,0 % | 69,4 % | 77,8 % |
| 976302 | 69,4 % | 77,8 % | 70,8 % | 70,8 % |
| 976303 | 69,4 % | 72,2 % | 77,8 % | 72,2 % |
| 976304 | 66,7 % | 77,8 % | 70,8 % | 73,6 % |
| 976305 | 63,9 % | 75,0 % | 69,4 % | 72,2 % |
| 976306 | 72,2 % | 66,7 % | 65,3 % | 73,6 % |

C1 liegt in fünf Seeds über und im sechsten unter C0. C2 liegt ebenfalls in
fünf Seeds über und im sechsten darunter, allerdings mit kleinen und
wechselnden Differenzen. C3 liegt bei DB Match in fünf Seeds über C0 und einmal
gleichauf; bei Exact Mutation liegt C3 in allen sechs Seeds über C0. C3 besitzt
zugleich die geringste Streuung der Bedingungsscores (DB: 1,8 Prozentpunkte;
Exact: 2,4 Prozentpunkte Standardabweichung).

## Faktorielles 2-x-2-Ergebnis

Die Komponentenwirkung wird primär über die faktoriellen Haupteffekte bestimmt,
nicht allein über C1-C0 und C2-C0.

| Effekt | DB Match | Exact Mutation | Seed-t-Intervall (DB / Exact) | Zweiweg-Bootstrap (DB / Exact) |
|---|---:|---:|---:|---:|
| A Semantik | +4,8 PP | +4,5 PP | [0,7; 8,9] / [0,4; 8,6] | [-0,6; 10,4] / [-1,2; 10,3] |
| B Kontrolle | +0,4 PP | +1,0 PP | [-1,8; 2,6] / [-1,6; 3,7] | [-4,7; 5,4] / [-4,5; 6,6] |
| A-x-B-Interaktion | -2,5 PP | -3,5 PP | -- | [-12,3; 8,1] / [-14,1; 8,1] |

A zeigt einen positiven mittleren Haupteffekt und bleibt in sämtlichen
Leave-one-seed-out-Auswertungen positiv (DB: +4,0 bis +5,8 Punkte; Exact: +3,6
bis +5,7 Punkte). B zeigt keinen belastbaren eigenständigen Haupteffekt. Die
negative Punktschätzung der Interaktion spricht gegen Additivität; ihr
Unsicherheitsintervall umfasst jedoch null.

Die Inferenz ist methodenabhängig: Seed- und taskbasierte t-Intervalle liegen
für A oberhalb null, der konservativere Zweiweg-Bootstrap über Aufgaben und
Seeds umfasst null. Daher wird A als konsistenter positiver Hinweis, nicht als
uneingeschränkt gesicherter universeller Effekt interpretiert. Für B ergibt
sich nach allen Verfahren kein belastbarer Effekt.

## Stabilität

| Bedingung | DB pass^6 | Exact pass^6 | DB pass@6 | Exact pass@6 |
|---|---:|---:|---:|---:|
| C0 Native | 27/80 = 33,8 % | 20/72 = 27,8 % | 79/80 = 98,8 % | 69/72 = 95,8 % |
| C1 Semantik | 28/80 = 35,0 % | 21/72 = 29,2 % | 78/80 = 97,5 % | 68/72 = 94,4 % |
| C2 Kontrolle | 30/80 = 37,5 % | 23/72 = 31,9 % | 79/80 = 98,8 % | 70/72 = 97,2 % |
| C3 Kombination | 32/80 = 40,0 % | 26/72 = 36,1 % | 79/80 = 98,8 % | 69/72 = 95,8 % |

C3 erreicht die höchste All-seed-Stabilität. Die sehr hohen pass@6-Werte aller
Bedingungen zeigen zugleich, dass fast jede Aufgabe von fast jeder Variante
mindestens einmal gelöst wird. Unterschiede betreffen damit vor allem die
wiederholbare Zuverlässigkeit, nicht eine grundsätzlich exklusive
Aufgabenfähigkeit.

## Saved/Broken und Mechanismusnähe

Gegenüber C0 ergeben sich beim DB Match für C1 78 Saved und 49 Broken
(netto +29), für C2 69 Saved und 61 Broken (netto +8) sowie für C3 83 Saved und
58 Broken (netto +25). Bei Exact Mutation lauten die entsprechenden Salden
+27, +12 und +24.

Von 1.190 C1-Kartenständen erreichten 529 einen Schreibkandidaten. In den
betroffenen C1-Zellen stehen 62 Saved 27 Broken gegenüber. Bei C3 erreichen
550 von 1.200 Kartenständen einen Schreibkandidaten; dort stehen 69 Saved 32
Broken gegenüber. Diese deskriptive Mechanismuskonsistenz stützt einen Beitrag
von A, ist aufgrund möglicher Trajektorienunterschiede aber kein isolierter
Mediatoreffekt.

B prüfte über C2 und C3 insgesamt 1.377 Schreibkandidaten. Der nachgelagerte
Mutation-Oracle-Abgleich markiert 199 Kandidaten als nicht mit der erwarteten
Mutation vereinbar. Davon wurden 142 unverändert freigegeben; 57 führten zu
`EVIDENCE_REQUIRED` oder `INVALID`. Zugleich löste B bei 70 oracle-kompatiblen
Kandidaten eine solche materielle Entscheidung aus. In Zellen mit materieller
B-Entscheidung ist der Saved/Broken-Saldo negativ (C2: 6/10; C3: 5/14 beim DB
Match). B ist damit technisch aktiv, besitzt in dieser Ausgestaltung aber nur
begrenzte Selektivität und keinen nachgewiesenen eigenständigen Nettonutzen.

## Aufwand

C1 verursacht gegenüber C0 im Mittel +45,3 % Agenten-API-Kosten und +26,3 %
Laufzeit. C3 verursacht +46,1 % Agenten-API-Kosten und +27,7 % Laufzeit. C2
verändert beide Größen praktisch nicht. Nachrichtenzahl und
Agenten-Tool-Aufrufe liegen bei allen drei Varianten nahe an C0; ihre
taskgeclusterten 95-%-Intervalle umfassen null. User-Simulator-Kosten werden
nicht als betrieblicher Agentenaufwand interpretiert.

## Zulässiges Gesamtfazit

Die Ergebnisse sind nicht mit der pauschalen Aussage vereinbar, alle Vorteile
seien lediglich bedeutungslose LLM-Randomness. A zeigt über sechs Seeds einen
positiven mittleren Haupteffekt, positive Leave-one-seed-out-Werte und einen
positiven Saved/Broken-Saldo in schreibverknüpften Fällen. Die Breite des
Zweiweg-Bootstraps und der negative sechste C1-Direktvergleich begrenzen jedoch
die Stärke der Kausal- und Generalisierbarkeitsaussage.

Die stärkste Ergebnisstory lautet deshalb: Semantische Unterstützung kann
Erfolg und wiederholbare Zuverlässigkeit erhöhen, verursacht aber ebenfalls
Regressionen und zusätzlichen Aufwand. Die deterministische Kontrolle ist in
der untersuchten Informationsgrenze technisch korrekt ausgeführt, erkennt aber
zu wenige fachlich falsche Kandidaten und erzeugt keinen belastbaren
eigenständigen Mehrwert. Die Kombination erzielt die höchste Stabilität, ihre
Interaktionspunktschätzung ist negativ, aber unsicher; ein additiver
Kombinationsvorteil ist damit nicht belastbar nachgewiesen.
