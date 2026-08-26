# Mechanismus-Audit von Komponente A

## Fragestellung und Abgrenzung

Der Audit untersucht alle 480 gepaarten C1–C0-Zellen der finalen Nano-Evaluation (80 Retail-Aufgaben, sechs Seeds). Er trennt vier Fragen, die nicht miteinander verwechselt werden dürfen:

1. Sind die in einer Karte gespeicherten Feldwerte durch die angegebenen Nutzeräußerungen belegt?
2. Wurde die Karte tatsächlich in den Kontext des nativen Agenten eingefügt?
3. War sie noch aktiv, als der native Agent eine Schreibaktion vorschlug?
4. Wechselte das Ergebnis gegenüber dem gepaarten nativen Lauf von falsch zu richtig oder von richtig zu falsch?

Die ersten drei Punkte prüfen die Funktionsfähigkeit und eine plausible Wirkungsmöglichkeit. Sie erlauben keinen direkten Einblick in die verborgene Modellverarbeitung und beweisen daher für einen Einzelfall nicht, dass ausschließlich die Karte die Entscheidung verursacht hat.

## Zentrale Befunde

Komponente A erkannte in 458 von 480 Zellen mindestens eine Bearbeitungsmöglichkeit. In 360 Zellen wurde mindestens eine Karte erzeugt und tatsächlich injiziert. In 318 Zellen war eine solche Karte aktiv, als der Agent einen schreibenden Werkzeugaufruf vorschlug. 345 Zellen enthielten eine Karte, die belegte Informationen aus mindestens zwei Nutzeräußerungen zusammenführte.

Die technische Belegtreue ist stark: Alle 7.807 akzeptierten Kartenfelder ließen sich unabhängig auf die jeweils angegebene Nutzeräußerung zurückführen. Für die beim Schreibkandidaten aktiven Karten gilt dies ebenfalls für alle 3.858 geprüften Felder. Alle 480 internen Trace-Audits bestanden. In 315 Zellen verwarf die deterministische Prüfung mindestens einen ungeeigneten Extraktionsbestandteil; elf Zellen enthielten ein kontrolliertes Fail-open-Ereignis. Die hohe Zahl verworfener Bestandteile zeigt zugleich, dass das vorgeschaltete semantische Modell häufig unsaubere Vorschläge erzeugte, die erst der deterministische Filter entfernte.

Die Belegtreue ist nicht mit semantischer Richtigkeit gleichzusetzen. Von 318 schreibbezogenen Karten enthielten 310 mindestens eine vom Benchmark erwartete Operation und 292 deckten alle erwarteten Operationstypen ab. Nur 122 enthielten jedoch ausschließlich erwartete Operationen; 196 führten zusätzliche Operationshypothesen mit. Von 938 direkt mit den erwarteten Schreibaktionen vergleichbaren Identifikatorfeldern stimmten 683 überein. Damit speichert A wörtlich belegte Werte zuverlässig, ordnet einzelne Äußerungen aber nicht durchgängig der richtigen Operation oder Argumentrolle zu.

## Zusammenhang mit den Ergebniswechseln

Über alle 480 DB-Match-Paare rettete C1 78 native Fehlschläge und beschädigte 49 native Erfolge. Der Nettogewinn beträgt somit 29 Zellen. Dieser Gewinn verteilt sich nicht gleichmäßig:

| Mechanismusstatus | Zellen | Gerettet | Beschädigt | Netto |
|---|---:|---:|---:|---:|
| keine Karte | 120 | 12 | 13 | −1 |
| Karte, aber kein Bezug zu einem Schreibkandidaten | 42 | 4 | 9 | −5 |
| Karte bei einem Schreibkandidaten aktiv | 318 | 62 | 27 | +35 |

Für Exact Mutation ergibt sich dasselbe Muster. Ohne Karte beträgt der Nettowert −1, mit Karte ohne Schreibbezug −8 und mit aktivem Schreibbezug +36. Unter den diskordanten Fällen ist das Verhältnis von geretteten zu beschädigten DB-Match-Zellen bei Schreibbezug günstiger als ohne Schreibbezug (Odds Ratio 3,16; zweiseitiger Fisher-Test, p = 0,0051). Für den strengen Endpunkt beträgt die deskriptive Odds Ratio 4,27 (p = 0,0007).

Diese Tests beschreiben eine Konzentration positiver Ergebniswechsel an der vorgesehenen Wirkstelle. Der Schreibbezug entsteht jedoch erst während der behandelten Trajektorie und ist nicht randomisiert. Die Werte sind deshalb Mechanismusevidenz, aber keine eigenständigen kausalen Effektschätzer.

Da der Schreibbezug voraussetzt, dass C1 überhaupt einen Werkzeugaufruf vorschlägt, wurde zusätzlich nur auf jene 366 DB-Match-Paare geblickt, in denen sowohl C0 als auch C1 tatsächlich mindestens eine Schreibaktion ausführten. Auch dort beträgt der Nettowert bei Schreibbezug +17 (43 gerettet, 26 beschädigt), ohne Schreibbezug dagegen 0 (7 gerettet, 7 beschädigt). Damit lässt sich das Muster nicht allein dadurch erklären, dass C1 in den verknüpften Fällen überhaupt geschrieben hat. Wegen der weiterhin nach der Behandlung gebildeten Gruppen bleibt auch diese Auswertung deskriptiv.

## Verteilung über die Seeds

Der Nettoeffekt der schreibbezogenen Zellen ist in keinem Seed negativ: +6, +8, 0, +9, +12 und 0 DB-Match-Zellen. Der insgesamt negative sechste Seed entsteht ausschließlich außerhalb dieses beobachtbaren Schreibbezugs. Das spricht gegen die einfache Erklärung, der aggregierte Vorteil beruhe nur auf einem einzelnen günstigen Seed. Es beseitigt die stochastische Unsicherheit jedoch nicht, weil auch bei aktivem Schreibbezug gerettete und beschädigte Fälle vorkommen.

## Konkrete Wirkpfade

Ein hilfreicher Fall ist Aufgabe 22, Seed 976303. Die Karte hielt mehrere, über den Dialog verteilte Adressänderungen auseinander. Der native C0-Lauf scheiterte; C1 führte die drei erwarteten Schreibaktionen vollständig aus und bestand DB Match sowie Exact Mutation.

Ein negativer Fall ist Aufgabe 3, Seed 976304. Die Karte führte Änderungen für zwei Bestellungen weiter. Der Agent führte neben der erwarteten Änderung eine zusätzliche Änderung an einer zweiten Bestellung aus. C0 war korrekt, C1 scheiterte. Dieser Fall zeigt, dass eine belegte, aber zu breit fortgeführte Zielmenge den Agenten auch schädigen kann.

Aufgabe 0 zeigt eine weitere Grenze: Mehrere Karten enthielten neben dem korrekten Austausch zusätzliche, fachlich unpassende Zahlungs- oder Bestelländerungshypothesen. Der anschließend vorgeschlagene Werkzeugaufruf blieb dennoch korrekt. Nicht jede semantische Unsauberkeit der Karte wird folglich handlungswirksam; sie bleibt aber ein vermeidbares Risiko und erklärt, warum reine Kartenaktivierung kein ausreichender Wirkungsnachweis ist.

## Belastbares Fazit

Die Ergebnisse widerlegen sowohl die Aussage „A bringt nachweislich immer etwas“ als auch die Aussage „der gesamte Vorteil ist bloße LLM-Zufälligkeit“.

Belastbar nachgewiesen ist:

- A erzeugt und injiziert einen deterministisch belegten, überwiegend schreibrelevanten Informationsspeicher.
- Der positive Nettoeffekt konzentriert sich an Zellen, in denen die Karte bei einem Schreibkandidaten aktiv ist.
- Dieses Muster ist über alle sechs Seeds nicht negativ und lässt sich nicht auf einen einzigen günstigen Seed reduzieren.
- Ergebniswechsel treten trotzdem in beide Richtungen auf; zusätzlich existieren gerettete Fälle ohne Karte.
- Die größte technische Grenze liegt nicht in der Quellenbelegung, sondern in der semantischen Zuordnung von Nutzeräußerungen zu Operationen und Argumentrollen.

Für die Thesis ist A deshalb als **funktionsfähiges, aber nicht fehlerfreies semantisches Unterstützungsartefakt** zu positionieren. Die Ergebnisverbesserung darf als durchschnittlicher C1-Effekt berichtet werden. Der Mechanismus-Audit stützt die Plausibilität des vorgesehenen Wirkpfads, rechtfertigt aber keine Behauptung, jeder gerettete Einzelfall sei eindeutig kausal durch die Karte entstanden.
