# Methodische Begründung der Sechs-Seed-Auswertung

Die Zahl von sechs Seeds wird nicht als allgemeingültige Mindestzahl oder als
Beweis für die Abwesenheit stochastischer Variation dargestellt. Colas,
Sigaud und Oudeyer (2018) zeigen, dass die erforderliche Wiederholungszahl von
Effektgröße, Varianz und gewünschter Teststärke abhängt. Deshalb wird die
Belastbarkeit hier über die beobachtete Verteilung, Unsicherheitsintervalle und
Sensitivitätsanalysen und nicht allein über die Seed-Anzahl beurteilt.

Reimers und Gurevych (2017) zeigen für nichtdeterministische NLP-Systeme, dass
ein einzelner Punktwert Systemvergleiche verzerren kann, und empfehlen die
Darstellung von Score-Verteilungen aus mehreren Ausführungen. Entsprechend
werden alle sechs Seedwerte, deren Standardabweichung und die Differenzen zu C0
berichtet.

Die vier bedingungsspezifischen Rohverteilungen werden gemeinsam mit ihrer
Paarung dargestellt. Überlappende Wertebereiche gelten als begrenzte
Trennschärfe, nicht automatisch als Beweis identischer Bedingungen. Für die
Wirkungsrichtung werden zusätzlich die Differenzen innerhalb desselben Seeds
betrachtet. Auf Aufgabenebene ergänzt die Verteilung der Erfolgsanzahl von 0/6
bis 6/6, wie häufig derselbe Fall zwischen Wiederholungen kippt. Die paarweise
Seedabweichung zählt dazu den Anteil diskordanter Seedpaare innerhalb derselben
Aufgabe. Beide Diagnosen sind deskriptiv und isolieren keine intrinsische
Modellrandomness von User-Simulator-, Provider- oder Trajektorienvariation.

Da sämtliche Bedingungen auf denselben Aufgaben und Seedwerten ausgeführt
werden, liegt ein gepaartes Design vor. Peyrard et al. (2021) begründen für
NLP-Evaluationen, warum die Paarung gemeinsamer Testinstanzen in Aggregation und
Testung erhalten bleiben muss. Die Auswertung verwendet deshalb zellweise
Differenzen zwischen jeder Intervention und C0 statt unabhängiger
Gruppenvergleiche.

Dror et al. (2018) betonen, dass Signifikanzverfahren an Metrik und
Abhängigkeitsstruktur des NLP-Versuchs angepasst werden müssen. Einzelne Zellen
werden daher nicht als unabhängig behandelt. Berichtet werden komplementär
taskbasierte, seedbasierte und gekreuzte Unsicherheitsanalysen.

Agarwal et al. (2021) zeigen für rechenintensive stochastische Benchmarks, dass
wenige Runs bei reinen Punktwertvergleichen zu instabilen Schlussfolgerungen
führen können, und empfehlen Intervallschätzungen sowie resamplingbasierte
Auswertungen über Aufgaben und Runs. Die Quelle stammt aus Deep Reinforcement
Learning und wird hier ausschließlich für die übertragbare statistische
Behandlung einer Task-x-Run-Matrix herangezogen. Der Zweiweg-Bootstrap zieht
Aufgaben- und Seedindizes unabhängig mit Zurücklegen und bildet bewusst die
Unsicherheit beider Dimensionen ab.

Die Leave-one-seed-out-Analyse prüft ergänzend, ob Richtung und Größenordnung
des Ergebnisses von einem einzelnen Seed abhängen. Sie ist eine
Sensitivitätsanalyse und kein eigener Signifikanztest. Saved/Broken und der
Mechanismus-Audit prüfen schließlich, ob aggregierte Differenzen mit
nachvollziehbaren Ergebnis- und Entscheidungswechseln vereinbar sind.

## Verwendete Kernquellen

- Colas, C., Sigaud, O., & Oudeyer, P.-Y. (2018). *How Many Random Seeds?
  Statistical Power Analysis in Deep Reinforcement Learning Experiments*.
  https://arxiv.org/abs/1806.08295
- Agarwal, R., Schwarzer, M., Castro, P. S., Courville, A. C., & Bellemare, M.
  (2021). *Deep Reinforcement Learning at the Edge of the Statistical
  Precipice*. NeurIPS 34.
  https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html
- Dror, R., Baumer, G., Shlomov, S., & Reichart, R. (2018). *The Hitchhiker's
  Guide to Testing Statistical Significance in Natural Language Processing*.
  ACL, 1383–1392. https://doi.org/10.18653/v1/P18-1128
- Peyrard, M., Zhao, W., Eger, S., & West, R. (2021). *Better than Average:
  Paired Evaluation of NLP Systems*. ACL-IJCNLP, 2301–2315.
  https://doi.org/10.18653/v1/2021.acl-long.179
- Reimers, N., & Gurevych, I. (2017). *Reporting Score Distributions Makes a
  Difference*. EMNLP, 338–348. https://doi.org/10.18653/v1/D17-1035
