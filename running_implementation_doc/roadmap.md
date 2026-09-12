# Roadmap

## Stand

`dev` trägt den vollständigen Stand (`ab6f5bd`), gepusht. Das Werkzeug ist am 12. September 2026 erstmals auf dem Zielrechner installiert worden; die Abnahme von Hand läuft. Dabei sind drei Befunde entstanden, die **vor** dem Abschluss der Abnahme zu beheben sind.

Die Werkbank `claude-workbench` steht einen Commit hinter `dev` und ist bei Gelegenheit nachzuziehen (`git merge --ff-only dev`).

## Phase 1 — Befunde aus der ersten Installation

### Schritt 1 — Die Hauptschleife dreht durch (schwerwiegend)

**Gemessen am laufenden Dienst:** 49 Schreibvorgänge von `state.json` in 2 Sekunden statt einem alle 30 Sekunden, 470 Sekunden Rechenzeit in 14 Minuten Laufzeit — gut ein halber Kern, dauerhaft. Rund 34.000 Unterprozesse in zwei Minuten (`nmcli`, `urbackupclientctl`, `systemctl`). Das Flackern des Live-Statusfensters war nur das sichtbare Symptom; die Schleife dreht auch ohne offenes Fenster.

**Ursache, isoliert nachgewiesen:** `watchdog` 3.0.0 meldet beim **bloßen Lesen** einer Datei ein `FileOpenedEvent`. Damit entsteht eine Rückkopplung:

```
Schleifendurchlauf
  → state.gather() → runtime.read_user_enabled()   oeffnet user-enabled
      → inotify FileOpenedEvent auf "user-enabled"
          → _TriggerHandler: Name steht in WATCHED_NAMES → _wake.set()
  → _wake.wait(30 s) kehrt sofort zurueck → naechster Durchlauf
```

**Bedingung:** Die Datei `/run/urbackup-gated/user-enabled` muss existieren. Beim Dienststart wird sie gelöscht, ein frisch gestarteter Dienst dreht also nicht durch — erst der erste Aufruf von `urbackup-gated-ctl activate` oder `deactivate` legt sie an. Am Zielrechner exakt nachvollzogen: Der Prozess-ID-Sprung im Journal beginnt unmittelbar nach dem Anlegen der Datei.

**Zu ändern:** `_TriggerHandler.on_any_event` darf nur auf Ereignisse reagieren, die eine Datei **verändern**. `FileOpenedEvent` und `FileClosedNoWriteEvent` gehören nicht dazu. Die Prüfung auf den Dateinamen bleibt.

**Sofortmaßnahme für den Betrieb, bis das behoben ist:** `systemctl --user restart urbackup-gated` beendet das Drehen, weil der Start die Datei löscht. Bei der Abnahme heißt das: Punkt 5 (Handschalter) löst das Verhalten erneut aus.

### Schritt 2 — Die Prüfung dafür existierte und stand an der falschen Stelle

Der Container-Prüfpunkt „own status writes do not wake the loop" misst acht Sekunden Ruhe — **bevor** der Handschalter-Test die Kommandodatei anlegt. Die Bedingung des Fehlers galt dort noch nicht, deshalb war er grün.

**Zu ändern:** Die Ruhemessung wiederholen, **nachdem** `user-enabled` existiert. Ohne das bleibt der Fehler nach der Korrektur genauso unbemerkt wie vorher. Dieselbe Art Fehler ist in dieser Sitzung dreimal aufgetreten (falsch-grüne Prüfpunkte, `yad`-Attrappe, hier) — die Prüfung stand jeweils dort, wo die Bedingung nicht galt.

### Schritt 3 — Statustext bei bewusst gestopptem Client

Zeigt der Status `service active: no`, steht darunter heute `status: not reachable (backend not running?)`. Das ist aus Sicht von UrBackup richtig, aber irreführend: Wir haben den Client selbst gestoppt. Eine Diagnose über seine Erreichbarkeit ist dann keine Information.

**Zu ändern:** Ist die Unit nicht aktiv, gehört dort ein `–` hin statt der Vermutung. Betrifft `state.format_status`.

### Offen, vor Schritt 3 zu klären

**Sind Notify-Meldungen ausgefallen?** Der Nutzer hat das beobachtet, die Belege sprechen dagegen: Kein `notify-send` hängt, der Dienst hat vier Threads (Normalwert), nur **eine** Zeile „notification held back" im Journal, und kein fehlgeschlagenes `notify-send` — das stünde seit der Korrektur von M5 dort. Im stabilen Zustand (Netz verboten, Client gestoppt) ist auch nichts zu melden.

Zu klären ist, welcher Fall vorlag:

- Der Client wurde **von Hand** gestartet oder gestoppt (`sudo systemctl` um 20:19 und 20:21) und der Wechsel „Sicherung läuft/läuft nicht" wurde nicht gemeldet → **echter Ausfall**, dann wird das ein eigener Schritt.
- Es wurde auf eine Meldung gewartet, während sich nichts änderte → kein Fehler.

## Phase 2 — Abnahme von Hand abschließen

Stufe 3, beschrieben in der Implementierungsdoku unter „Stufe 3: Abnahme von Hand". Aus der ersten Installation bereits **bestanden**:

- Installation läuft sauber durch, Symlink landet in `graphical-session.target.wants` — die Bindung an die grafische Sitzung greift.
- Der Dienst läuft auf `/usr/bin/python3 -u -m urbackup_gated.daemon`.
- `urbackup-gated-ctl status` und `-h` sind brauchbar, `activate`/`deactivate` wirken.
- Der Installer stoppt und deaktiviert `urbackupclientbackend` wie vorgesehen.
- **Punkt 3 (echter Netzwechsel):** Wechsel von `lieluxVPN` auf `lieluX` hat den Client gestartet, Meldung kam, Serververbindung wurde gemeldet.

**Noch offen:** Punkt 1 (Schaltflächen und Anzeigedauer), Punkt 2 (Live-Fenster — erst nach Schritt 1 sinnvoll, es flackerte), Punkt 4 (Dockingstation), Punkt 5 (Handschalter — löst bis zur Korrektur das Drehen aus), Punkt 6 (Fehlerfenster des Fail-safe), Punkt 7 (Abmelden), Punkt 8 (erstes echtes Backup).

Punkt 8 bleibt die **einzige inhaltlich offene Annahme** des Vorhabens: Ob die Fortschrittszahlen aus `urbackupclientctl status` stimmen, zeigt erst die erste echte Sicherung.

## Nicht vergessen

Das Container-Abbild `urbackup-gated-tests` liegt nach den Prüfläufen mit `KEEP_IMAGE=1` noch auf dem Rechner — einige hundert Megabyte. Nach der Abnahme kann es weg: `docker image rm urbackup-gated-tests`.

Zwei echte Netznamen stehen weiterhin im öffentlichen Repository: `lieluX` und `lielux` in der Implementierungsdoku als Begründung für den case-sensitiven Vergleich, `lieluX` in den Testszenarien. Aus der ausgelieferten Konfiguration sind sie entfernt. Ob das genügt, ist eine Entscheidung, keine Aufgabe.
