# 1 Zusammenhänge

## Ausgangslage und Ziel

XPS-Linux läuft mit aktiviertem UrBackup-Internet-Modus zuverlässig (Datenplan-Limit
und Auth-Handshake sind inzwischen behoben). Offen bleibt ein Fall, den UrBackup
selbst nicht lösen kann: Der Rechner hängt gelegentlich per Handy-Hotspot am Netz,
mit einem echten, knappen Mobilfunk-Datenlimit (2–3 GB/Monat). UrBackups eingebaute
"getaktete Verbindung"-Erkennung ist ausschließlich für Windows implementiert
(bestätigt im Quellcode, `urbackupclient/win_network_cost.h`) und greift unter
Linux nicht.

Ziel: Ein eigener, kleiner Dienst entscheidet anhand der aktuellen Netzwerkverbindung,
ob der `urbackupclientbackend`-Dienst laufen darf, und startet/stoppt ihn entsprechend.
Zusätzlich übernimmt er, weil er ohnehin den Zustand kennt, eine Desktop-Status-
anzeige per `notify`, die es für UrBackup unter Linux von Haus aus nicht gibt.

## Dienstname

Festgelegt: **`urbackup-gated`** — kürzer als der ursprüngliche Arbeitstitel
`urbackup-watcherd`, folgt aber weiterhin der üblichen Konvention, dass ein Dämon
mit einem `d` am Ende benannt wird. Systemd-Unit entsprechend
`urbackup-gated.service`, Konfigurationsordner `/etc/urbackup-gated`.

## Systemintegration und Rechteaufteilung

`urbackup-gated` läuft als `systemd --user`-Dienst, nicht als System-Dienst —
startet also erst mit der Anmeldung und endet mit der Abmeldung. Das entspricht
der gewollten Regel „Sicherung läuft nur, wenn angemeldet". Desktop-Notifications
laufen dadurch ganz natürlich in der eigenen Sitzung, ohne Umweg über eine fremde
D-Bus-Session.

`urbackupclientbackend.service` bleibt ein System-Dienst mit Root-Rechten
(unverändert). Damit `urbackup-gated` ihn dennoch steuern kann, ohne selbst Root
zu sein, bekommt es über `sudoers` eine eng gefasste, passwortlose Freigabe für
genau zwei Befehle: `systemctl start urbackupclientbackend.service` und
`systemctl stop urbackupclientbackend.service` — keine weiteren Rechte.

`urbackupclientbackend.service` wird aus dem automatischen Systemstart genommen
(`systemctl disable`, nicht `mask`), damit es nicht schon vor der Anmeldung mit
Root-Rechten hochkommt. Einzige Instanz, die es je startet oder stoppt, ist
`urbackup-gated`.

**Selbstheilung nach Neuinstallation:** Das offizielle UrBackup-Installationsskript
(`install_client_linux.sh`) ruft bedingungslos bei jedem Lauf
`systemctl enable urbackupclientbackend.service` gefolgt von `systemctl start`
auf (verifiziert im Quellcode, Zeilen 342/349) — unabhängig davon, ob der Dienst
vorher bewusst deaktiviert war. Eine manuelle Neuinstallation des UrBackup-Clients
würde also den System-Autostart mit Root-Rechten wieder aktivieren und sofort
starten, bevor sich jemand anmeldet. Um nicht auf manuelles Nacharbeiten angewiesen
zu sein, prüft und erzwingt `urbackup-gated` bei **jedem eigenen Start** erneut
`systemctl disable urbackupclientbackend.service` — nicht nur einmalig bei der
Ersteinrichtung. Damit repariert sich der Zustand spätestens bei der nächsten
Anmeldung nach einer Neuinstallation von selbst.

## Entscheidungsregel

- Ethernet-Verbindung vorhanden → UrBackup darf immer laufen.
- WLAN-Verbindung vorhanden → UrBackup darf nur laufen, wenn die aktuelle SSID auf
  einer konfigurierten Erlaubnisliste steht.
- Weder Ethernet noch eine erlaubte WLAN-SSID → UrBackup wird gestoppt/bleibt gestoppt.
- Sind mehrere Interfaces gleichzeitig aktiv (z. B. Docking-Ethernet und WLAN
  parallel), reicht eine einzige qualifizierende Verbindung, damit gestartet wird.

## Auslösepunkte (Trigger)

1. Dienststart selbst (führt sofort eine volle Netzwerkprüfung durch).
2. Verbindungsauf-/-abbau (event-getrieben, z. B. über NetworkManager-Dispatcher).
3. Zeitgesteuert alle 30 Sekunden (Fallback, falls ein Event verpasst wird) — bei
   diesem Trigger und beim Dienststart wird die Netzwerkverbindung zusätzlich aktiv
   geprüft (nicht nur der zuletzt gemeldete Event-Zustand).

## Verhalten bei Netzwechsel während laufender Sicherung

Wechselt die WLAN-SSID während einer aktiven Sicherung ins Verbotene oder
entfällt die Verbindung ganz (z. B. Wechsel vom erlaubten Netz zum
Handy-Hotspot), stoppt `urbackup-gated` sofort — nicht erst nach Ende der
laufenden Sicherung. Reine Sicherheitsfrage fürs mobile Datenvolumen: Eine
100-GB-Sicherung „zu Ende laufen zu lassen" könnte das Datenlimit im Zweifel
ohnehin selbst erschöpfen, bevor sie fertig ist.

„Sofort stoppen" heißt hier `systemctl stop urbackupclientbackend.service` —
das ist kein Abwürgen, sondern ein geordnetes Stoppen des Dienstes. Eine
feinere, clientseitige Möglichkeit, nur den laufenden Sicherungsjob gezielt
abzubrechen, gibt es ohnehin nicht: `urbackupclientctl` kennt ausschließlich
`start`, `status`, `browse`, `restore-start`, `set-settings`, `reset-keep`,
`add-backupdir`, `list-backupdirs`, `remove-backupdir` — kein `stop`/`abort`/
`pause` (verifiziert per `--help`). Der Dienst-Stopp ist damit nicht nur die
gewählte, sondern die einzige clientseitig überhaupt vorhandene Option.
UrBackup nimmt eine so unterbrochene Sicherung später von selbst wieder auf,
wie wir bei der Fehlersuche am eigentlichen UrBackup-Client mehrfach
beobachtet haben.

## Zustand, Merken zwischen Aufrufen und Statusabfrage

Fester, bekannter Pfad `/run/urbackup-gated/state.json` statt der ursprünglichen
Idee einer UUID-Datei unter `/tmp`. `/run` ist per Definition ein tmpfs und wird
bei jedem Neustart automatisch geleert — das erfüllt genau den gewünschten Zweck
("Datei weg = Ausgangslage klar nach Neustart"), ist aber unter einem festen,
auffindbaren Namen leichter zu debuggen als eine zufällige UUID-Datei.

**Festgelegt:** Dort wird nicht nur der reine Boot-Merker abgelegt, sondern der
**vollständige Status** — erkannte Netzwerklage (Ethernet ja/nein, aktive SSID),
getroffene Entscheidung samt Begründung, sowie der UrBackup-Client-Status
(`urbackupclientctl status`, s. u.). Es gibt dafür genau eine Backend-Funktion
„vollständigen Status ermitteln/aufbereiten", die von drei Stellen verwendet wird:

1. **Der Dienst selbst** — ruft sie bei jedem Trigger (Start, Netzwechsel,
   30-Sekunden-Takt) auf und schreibt das Ergebnis nach `state.json`.
2. **Das Zenity-Detailfenster** beim Notify-Klick (s. u.) — ruft dieselbe
   Funktion live neu auf, da es im selben Prozess läuft; kein Umweg über die
   Datei nötig, dadurch tagesaktuellster Stand.
3. **Ein separates Kommandozeilen-Statuswerkzeug** (löst die „Testbarkeit"-Frage
   aus dem Konzept) — liest nur `state.json` und zeigt sie lesbar an, ohne
   selbst etwas neu zu ermitteln. Dadurch höchstens rund 30 Sekunden alt
   (Zeittrigger-Intervall), aber ohne eigene Berechtigungen/Logik-Duplizierung.
   Ersetzt die ursprünglich angedachte separate Dry-Run-Logik: Ein eigener
   Entscheidungs-Simulator wäre nötig gewesen, wenn der Dienst selbst befragt
   werden sollte, ohne dass er läuft — da er aber ohnehin läuft, reicht das
   Auslesen seines echten, aktuellen Zustands.

Die eigentliche Ermittlungslogik existiert damit nur ein einziges Mal im Code.

## Notify-Meldungen

- Beim tatsächlichen Starten des UrBackup-Clients.
- Beim tatsächlichen Stoppen des UrBackup-Clients.
- Bei Zustandswechsel "Sicherung aktiv" ↔ "Sicherung inaktiv" (erkannt bei den
  Zeittriggern).
- Wenn keine Sicherung läuft: alle 2 Stunden (bei einem der Zeittrigger) eine kurze
  Meldung, ob eine Verbindung zum Server besteht.
- Wenn eine Sicherung läuft: alle 15 Minuten ein kurzer Fortschrittsstatus.
- Anzeigedauer 5 Sekunden, konfigurierbar.

Datenquelle für Serververbindung/Sicherungsfortschritt: `urbackupclientctl status`
(JSON-Ausgabe). Die relevanten Felder, alle im Quellcode verifiziert
(`urbackupclient/ClientServiceCMD.cpp`, `urbackupserver/FileBackup.cpp`,
`urbackupclient/InternetClient.cpp`):

- `action` — Klartext-Kürzel des laufenden Vorgangs (`INCR`, `FULL`, `FULLI`,
  `INCRI`, `R_INCR`, `R_FULL`, `RESTORE_IMAGE`, `RESTORE_FILES`).
- `total_bytes`/`done_bytes` — vom Server durchgereichte Zählerstände, nicht
  clientseitig berechnet.
- `speed_bpms` — ebenfalls vom Server durchgereicht, aber **kein** Mittelwert
  über den ganzen Lauf: gleitendes Fenster von gut 10 Sekunden
  (`calculateDownloadSpeed`, Neuberechnung nur wenn `ctime - speed_set_time >
  10000` ms).
- `time_since_last_lan_connection` — Millisekunden seit dem letzten reinen
  LAN-Kontakt (`InternetClient::hasLANConnection()`, wird ausdrücklich nur bei
  `!internet_conn` aufgerufen). Für XPS-Linux im Internet-Modus **nicht**
  als Verbindungsindikator brauchbar, da Internet-Modus-Kontakte diesen Wert
  nie zurücksetzen. Für „ist überhaupt eine Serververbindung da" sind
  `internet_connected` und `servers[]` die richtigen Felder.
- `server_status_id` — reine, vom Server vergebene Kennnummer zur
  Job-Zuordnung, ohne eigene inhaltliche Bedeutung.

### Klickbare Notification mit Detailanzeige

Live getestet (Skript `notify_click_test.py`, danach entfernt) und
bestätigt funktionsfähig: `notify-send -A "default=..." -A "details=..."`
zeigt auf diesem Desktop tatsächlich einen klickbaren Button, und die
gewählte Aktion kommt als Text auf stdout beim aufrufenden Prozess an — ganz
ohne eigene D-Bus-Anbindung. Klickt man auf „Details", öffnet derselbe
Prozess im Anschluss `zenity --info`/`--text-info` mit dem vollständigen
`urbackupclientctl status`. Es gibt keine unabhängige Verbindung zwischen
Notify-Klick und Zenity — der aufrufende Prozess blockiert (`--action`
impliziert `--wait`), bekommt die Klick-Antwort direkt zurück und entscheidet
im selben Ablauf, ob er Zenity startet.

Konsequenz für die Umsetzung: Da dieser Aufruf blockiert, darf er nicht in
der Haupt-Schleife des Dienstes laufen (sonst steht die 30-Sekunden-Prüfung
still, solange eine Notification unbeantwortet auf dem Bildschirm hängt) —
er muss in einem eigenen Thread/Hintergrundprozess erfolgen.

Die ursprüngliche Sorge, ein klickbarer Button könnte die gewünschten 5
Sekunden Anzeigedauer unterlaufen, hat sich als unbegründet erwiesen: Live
beobachtet läuft die Anzeigedauer normal ab; sie pausiert nur, solange der
Mauszeiger über der Notification steht (verbreitetes, gewolltes Verhalten
vieler Notification-Server, kein UrBackup-gated-spezifisches Problem).

**Gedankenoption, nicht entschieden:** Ein bereits offenes Zenity-Textfenster
(`zenity --text-info --auto-scroll`, gefüttert über eine offen gehaltene
stdin-Pipe) lässt sich laufend mit neuem Text aktualisieren und bleibt dabei
dasselbe Fenster — live getestet und bestätigt (`--auto-scroll`: „Nur wenn
Text von Standardeingabe aufgenommen wird", `zenity --help-text-info`).
Damit wäre eine dauerhaft offene, sich selbst aktualisierende Statusanzeige
technisch möglich. Ob das gewollt ist, ist offen — bisher nur als Idee
festgehalten.

**Systemintegration bestätigt:** Der komplette Ablauf (Notification mit
Button → Klick-Erkennung → Zenity-Fenster mit Live-Update) funktioniert
nachweislich unverändert, wenn er nicht interaktiv im Terminal, sondern aus
einem echten `systemd --user`-Dienst heraus gestartet wird (Testaufbau:
`urbackup-gated-test.service`, danach entfernt) — die Sorge, ein
`systemd --user`-Dienst könnte die Desktop-Umgebung (Anzeige/D-Bus) nicht
erben, hat sich für dieses System nicht bestätigt.

## Konfiguration

Eigene Datei/Ordner: `/etc/urbackup-gated`. Muss mindestens enthalten: Liste
erlaubter SSIDs, Anzeigedauer der Notify-Meldungen, ggf. die beiden Intervalle
(2 h / 15 min), falls sie einstellbar sein sollen statt fest im Code.

Aktuell genannte SSIDs: `lieluX`, `lielux`, `lieluxVPN`, `HZDR` — geklärt: kein
Tippfehler, `lieluX` und `lielux` sind zwei tatsächlich unterschiedliche, echte
Netze. Vergleich bleibt case-sensitiv.

### Fail-safe bei fehlender/kaputter Konfiguration

Fehlt `/etc/urbackup-gated`, ist sie nicht lesbar oder inhaltlich fehlerhaft
(z. B. keine gültige SSID-Liste), bleibt `urbackupclientbackend` **gestoppt**
bzw. wird gestoppt — unabhängig davon, welches Netz gerade aktiv ist. Sicherer
Default: eine verpasste Sicherungsgelegenheit ist unkritisch, eine ungeprüft
laufende Sicherung über ein möglicherweise nicht erlaubtes Netz wäre genau
das Risiko, das der Dienst verhindern soll.

Keine eigene Notify-Meldung für diesen Fall — der Nutzer erkennt den
Fehlzustand indirekt am Ausbleiben der gewohnten Verbindungs-/
Sicherungsmeldungen. Stattdessen ein **Zenity-Fehlerfenster** mit der
konkreten Fehlerursache, das per Klick auf „OK" quittiert werden muss. Damit
weiß der Nutzer gezielt, was kaputt ist, und kann `urbackupclientbackend` im
Zweifel manuell starten, statt nur zu bemerken, dass „nichts mehr kommt".

## Protokollierung

Festgelegt: normale Ausgabe auf stdout/stderr, kein eigenes Logfile. Landet
dadurch automatisch im systemd-Journal (`journalctl --user -u urbackup-gated`)
und braucht keine eigene Rotation/Aufräumlogik.

## Technische Bausteine

Festgelegt: Sprache **Python**.

Festgelegt: Notify per **`notify-send`-Subprozessaufruf** (aus `libnotify-bin`),
keine eigene D-Bus-Bibliothek — live getestet und bestätigt funktionsfähig
(s. „Klickbare Notification mit Detailanzeige").

### Netzwerk-Ereigniserkennung

Festgelegt: **Trigger-Datei + inotify**, nicht Unix-Signal oder eigener
D-Bus-Dienst. Der NetworkManager-Dispatcher (läuft als **root**, Skript unter
`/etc/NetworkManager/dispatcher.d/`, ausgelöst bei den Aktionen `up`, `down`,
`vpn-up`, `vpn-down` u. a. — vollständige Liste per
`man NetworkManager-dispatcher`) berührt nur eine Datei; `urbackup-gated`
beobachtet sie per inotify (z. B. Python-`watchdog`) und löst darauf sofort
eine Prüfung aus. Dazu weiterhin der 30-Sekunden-Timer im Dienst selbst als
Fallback, falls ein Event verpasst wird.

Begründung gegenüber den Alternativen: Ein Unix-Signal an die Prozess-ID des
Dienstes wäre im Programmumfang minimal einfacher gewesen, hätte aber eine
Fehlerquelle über eine potenziell veraltete PID-Datei (Dienst neu gestartet,
alte PID-Datei noch vorhanden). Ein eigener D-Bus-Dienst hätte root gezwungen,
gezielt die Session-Bus-Adresse des richtigen Nutzers zu ermitteln, mit
deutlich mehr beweglichen Teilen. Die Trigger-Datei umgeht beide Probleme:
kein PID-Verfall, keine Root-zu-Nutzer-Adressierung — root kann in die vom
Dienst angelegte Datei problemlos schreiben, keine gesonderte Rechteklärung
nötig.

### Aktuelle SSID/Verbindungsart ermitteln

Festgelegt: **`nmcli`** per Subprozess, mit `-t` (terse, maschinenlesbares
Format) und `-f` (gezielte Felder, z. B. `TYPE,STATE,CONNECTION`) — passend
zum bisherigen Muster bei Notify.

Sprachabhängigkeit der Ausgabe ist damit vollständig beseitigt, nicht nur
verringert: Laut `nmcli`-Handbuch, Abschnitt „INTERNATIONALIZATION NOTES",
hängt die Ausgabe grundsätzlich von der Locale-Umgebung ab; die dort selbst
empfohlene, verlässliche Lösung ist der Aufruf als `LC_ALL=C nmcli …`. `-t`
regelt nur das Format (maschinenlesbare Feldtrennung), nicht die Sprache der
Werte — beides zusammen (`LC_ALL=C nmcli -t -f …`) ist notwendig und
laut Handbuch ausreichend.

# 2 Vorgaben

_Noch nicht ausgearbeitet._

# 3 Einheiten

_Noch nicht ausgearbeitet._

# Anhang

_Noch nicht ausgearbeitet._
