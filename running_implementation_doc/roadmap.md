# Roadmap

## Stand

`dev` trägt den vollständigen Stand. Das Werkzeug ist am 12. September 2026 erstmals auf dem Zielrechner installiert worden; die Abnahme von Hand läuft. Von den drei Befunden der ersten Installation sind zwei behoben (`b84dd3b`, `edb8623`), einer steht noch aus.

**Auf dem Zielrechner läuft weiterhin der alte Stand.** Die Korrektur der Hauptschleife wirkt dort erst nach einer Neuinstallation von `dev` — bis dahin löst der Handschalter das Durchdrehen erneut aus, und `systemctl --user restart urbackup-gated` beendet es wieder.

Die Werkbank `claude-workbench` steht hinter `dev` und ist bei Gelegenheit nachzuziehen (`git merge --ff-only dev`).

## Phase 1 — Befunde aus der ersten Installation

### Schritt 3 — Statustext bei bewusst gestopptem Client

Zeigt der Status `service active: no`, steht darunter heute `status: not reachable (backend not running?)`. Das ist aus Sicht von UrBackup richtig, aber irreführend: Wir haben den Client selbst gestoppt. Eine Diagnose über seine Erreichbarkeit ist dann keine Information.

**Zu ändern:** Ist die Unit nicht aktiv, gehört dort ein `-` hin statt der Vermutung. Betrifft `state.format_status`.

### Offen, vor Schritt 3 zu klären

**Sind Notify-Meldungen ausgefallen?** Der Nutzer hat das beobachtet, die Belege sprechen dagegen: Kein `notify-send` hängt, der Dienst hat vier Threads (Normalwert), nur **eine** Zeile „notification held back" im Journal, und kein fehlgeschlagenes `notify-send` — das stünde seit der Korrektur von M5 dort. Im stabilen Zustand (Netz verboten, Client gestoppt) ist auch nichts zu melden.

Zu klären ist, welcher Fall vorlag:

- Der Client wurde **von Hand** gestartet oder gestoppt (`sudo systemctl` um 20:19 und 20:21) und der Wechsel „Sicherung läuft/läuft nicht" wurde nicht gemeldet → **echter Ausfall**, dann wird das ein eigener Schritt.
- Es wurde auf eine Meldung gewartet, während sich nichts änderte → kein Fehler.

### Beobachtet, nicht aufgeklärt

Der Container-Prüfpunkt „without any connection the running client is left alone" war bei der Abnahme einmal rot und danach grün, ohne erklärte Ursache. Beim Gegenbeweis zu Schritt 2 ist er zusammen mit der drehenden Schleife rot geworden und ohne sie grün — je eine Beobachtung pro Richtung, kein Beweis.

Der Zwischenmechanismus ist **nicht** bekannt. Die naheliegende Vermutung trägt nicht: Das Wettrennen zwischen dem Setzen der Szenariodatei und der `nmcli`-Attrappe, die sie liest, endet in einem fehlschlagenden `nmcli`, und das führt zu `effective = None` und damit zu *keiner* Handlung — es kann den Client also nicht stoppen. Was ihn in diesem Moment stoppt, ist offen.

Solange der Prüfpunkt grün bleibt, ist das keine Aufgabe. Wird er wieder rot, beginnt hier die Spur.

## Phase 2 — Abnahme von Hand abschließen

Stufe 3, beschrieben in der Implementierungsdoku unter „Stufe 3: Abnahme von Hand". Aus der ersten Installation bereits **bestanden**:

- Installation läuft sauber durch, Symlink landet in `graphical-session.target.wants` — die Bindung an die grafische Sitzung greift.
- Der Dienst läuft auf `/usr/bin/python3 -u -m urbackup_gated.daemon`.
- `urbackup-gated-ctl status` und `-h` sind brauchbar, `activate`/`deactivate` wirken.
- Der Installer stoppt und deaktiviert `urbackupclientbackend` wie vorgesehen.
- **Punkt 3 (echter Netzwechsel):** Wechsel von `lieluxVPN` auf `lieluX` hat den Client gestartet, Meldung kam, Serververbindung wurde gemeldet.

**Noch offen:** Punkt 1 (Schaltflächen und Anzeigedauer), Punkt 2 (Live-Fenster), Punkt 4 (Dockingstation), Punkt 5 (Handschalter), Punkt 6 (Fehlerfenster des Fail-safe), Punkt 7 (Abmelden), Punkt 8 (erstes echtes Backup).

Punkt 2 und Punkt 5 setzen die Neuinstallation von `dev` voraus — mit dem alten Stand flackert das Fenster und der Handschalter startet das Durchdrehen.

Punkt 8 bleibt die **einzige inhaltlich offene Annahme** des Vorhabens: Ob die Fortschrittszahlen aus `urbackupclientctl status` stimmen, zeigt erst die erste echte Sicherung.

## Nicht vergessen

Das Container-Abbild `urbackup-gated-tests` liegt nach den Prüfläufen mit `KEEP_IMAGE=1` noch auf dem Rechner — einige hundert Megabyte. Nach der Abnahme kann es weg: `docker image rm urbackup-gated-tests`.

Zwei echte Netznamen stehen weiterhin im öffentlichen Repository: `lieluX` und `lielux` in der Implementierungsdoku als Begründung für den case-sensitiven Vergleich, `lieluX` in den Testszenarien. Aus der ausgelieferten Konfiguration sind sie entfernt. Ob das genügt, ist eine Entscheidung, keine Aufgabe.
