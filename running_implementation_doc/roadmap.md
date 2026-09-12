# Roadmap

## Stand

Alle drei Befunde der ersten Installation sind behoben: die durchdrehende Hauptschleife (`b84dd3b`), die Ruhemessung an der falschen Stelle (`edb8623`) und der irreführende Statustext (`3940618`). `dev` und `claude-workbench` stehen auf demselben Stand und sind gepusht.

Damit bleibt als offene Arbeit nur noch die Abnahme von Hand. Die Neuinstallation auf dem Zielrechner von `dev` läuft zum Zeitpunkt dieses Eintrags (12. September 2026); erst danach sind die Abnahmepunkte 2 und 5 prüfbar.

## Abnahme von Hand abschließen

Stufe 3, beschrieben in der Implementierungsdoku unter „Stufe 3: Abnahme von Hand". Aus der ersten Installation bereits **bestanden**:

- Installation läuft sauber durch, Symlink landet in `graphical-session.target.wants` — die Bindung an die grafische Sitzung greift.
- Der Dienst läuft auf `/usr/bin/python3 -u -m urbackup_gated.daemon`.
- `urbackup-gated-ctl status` und `-h` sind brauchbar, `activate`/`deactivate` wirken.
- Der Installer stoppt und deaktiviert `urbackupclientbackend` wie vorgesehen.
- **Punkt 3 (echter Netzwechsel):** Wechsel von `lieluxVPN` auf `lieluX` hat den Client gestartet, Meldung kam, Serververbindung wurde gemeldet.

**Noch offen:** Punkt 1 (Schaltflächen und Anzeigedauer), Punkt 2 (Live-Fenster), Punkt 4 (Dockingstation), Punkt 5 (Handschalter), Punkt 6 (Fehlerfenster des Fail-safe), Punkt 7 (Abmelden), Punkt 8 (erstes echtes Backup).

Punkt 8 bleibt die **einzige inhaltlich offene Annahme** des Vorhabens: Ob die Fortschrittszahlen aus `urbackupclientctl status` stimmen, zeigt erst die erste echte Sicherung.

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

Das Container-Abbild `urbackup-gated-tests` liegt nach den Prüfläufen mit `KEEP_IMAGE=1` noch auf dem Rechner — einige hundert Megabyte. Nach der Abnahme kann es weg: `docker image rm urbackup-gated-tests`.

Zwei echte Netznamen stehen weiterhin im öffentlichen Repository: `lieluX` und `lielux` in der Implementierungsdoku als Begründung für den case-sensitiven Vergleich, `lieluX` in den Testszenarien. Aus der ausgelieferten Konfiguration sind sie entfernt. Ob das genügt, ist eine Entscheidung, keine Aufgabe.
