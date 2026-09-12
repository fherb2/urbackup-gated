# Roadmap

## Stand

**Version 1.0.0 ist freigegeben.** Die Abnahme von Hand ist in allen acht Punkten bestanden, geprüft am 12. September 2026 auf dem Zielrechner; damit ist auch die zuletzt noch offene Geschwindigkeitsangabe gemessen und bestätigt. Beide automatischen Teststufen laufen vollständig durch, kein Modul ist ungeprüft. Der Code-Review und die Befunde der ersten Installation sind abgearbeitet.

Die Anwendung ist entsprechend ihrer Dokumentation nutzbar. **Offene Arbeit gibt es nicht mehr** — was unten steht, sind Spuren für den Fall, dass eine Beobachtung wiederkehrt, und eine Entscheidung, die dem Nutzer gehört.

## Zurückgestellt

Beides ist bewusst keine Aufgabe. Es steht hier, damit die Spur wiederauffindbar ist, falls die Beobachtung erneut auftritt.

### Sind Notify-Meldungen ausgefallen?

Bei der ersten Installation beobachtet, aber nicht mehr aufklärbar: Ob das Live-Statusfenster zum fraglichen Zeitpunkt (20:19/20:21) bereits offen war, ließ sich nachträglich nicht feststellen — und genau daran hängt die Antwort. Solange das Fenster offen ist, werden die Meldungen nach Festlegung unterdrückt (siehe „Dauerhaft offenes, live aktualisierendes Statusfenster", Punkt „Nur ein Fenster gleichzeitig"), und der gemerkte Vorzustand wandert dabei weiter, sodass nichts nachgereicht wird.

Die übrigen Belege sprechen gegen einen Ausfall: Kein hängendes `notify-send`, der Dienst mit vier Threads (Normalwert), nur **eine** Zeile „notification held back" im Journal, und kein fehlgeschlagenes `notify-send` — das stünde seit der Korrektur von M5 dort.

Wieder aufzunehmen, wenn ein Wechsel „Sicherung läuft/läuft nicht" oder „Server verbunden/nicht verbunden" ohne offenes Statusfenster unbemerkt bleibt.

### Der Prüfpunkt „without any connection the running client is left alone"

War bei der Abnahme einmal rot und danach grün. Beim Gegenbeweis zu Schritt 2 ist er zusammen mit der drehenden Schleife rot geworden und ohne sie grün — je eine Beobachtung pro Richtung, kein Beweis.

Der Zwischenmechanismus ist **nicht** bekannt. Die naheliegende Vermutung trägt nicht: Das Wettrennen zwischen dem Setzen der Szenariodatei und der `nmcli`-Attrappe, die sie liest, endet in einem fehlschlagenden `nmcli`, und das führt zu `effective = None` und damit zu *keiner* Handlung — es kann den Client also nicht stoppen. Was ihn in diesem Moment stoppt, ist offen.

Wieder aufzunehmen, wenn der Prüfpunkt erneut rot wird.

## Nicht vergessen

Zwei echte Netznamen stehen weiterhin im öffentlichen Repository: `lieluX` und `lielux` in der Implementierungsdoku als Begründung für den case-sensitiven Vergleich, `lieluX` in den Testszenarien. Aus der ausgelieferten Konfiguration sind sie entfernt. Ob das genügt, ist eine Entscheidung, keine Aufgabe.
