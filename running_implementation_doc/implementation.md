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
anzeige per `notify`, die es für UrBackup unter Linux von Haus aus nicht gibt. Weiterhin soll dort per Button eine Detailanzeige des aktuellen Zustands als yad Popup implementiert werden.

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

## Entscheidungsregeln

Bewertet werden **alle gleichzeitig aktiven physischen Verbindungen**, nicht nur eine ausgewählte:

- Irgendeine aktive WLAN-Verbindung, deren SSID **nicht** auf der Erlaubnisliste steht → verboten. Läuft der UrBackup-Client, wird er gestoppt; läuft er nicht, wird er nicht gestartet. Das gilt auch dann, wenn parallel eine Ethernet-Verbindung besteht.
- Sonst, sofern mindestens eine aktive Verbindung vorhanden ist (Ethernet, oder WLAN mit erlaubter SSID) → erlaubt. Läuft der Client nicht, wird er gestartet; läuft er, läuft er weiter.
- Gar keine aktive Netzwerkverbindung → **keine** Entscheidung, der Client bleibt in seinem aktuellen Zustand: gestoppt oder laufend.

Die so ermittelte Erlaubnis ist nur die eine Hälfte; sie wird mit dem manuellen Nutzer-Zustand verundet (siehe „Manuelles Aktivieren und Deaktivieren").

**Warum diese bewusst strenge Form, und was sie ersetzt:** Das eigentliche Risiko ist, dass die Verbindung zum Server über eine volumenbeschränkte WLAN-Verbindung läuft, obwohl parallel ein unbeschränkter Kanal online ist — Routing-Entscheidungen sind von außen nicht zuverlässig vorhersagbar. Der naheliegende Weg wäre, per Routing-Abfrage zu ermitteln, über welches Interface der konfigurierte UrBackup-Server tatsächlich erreicht wird. Dieser Weg ist verworfen: Er verlangt die Serveradresse, deren Namensauflösung und — sobald der Weg durch einen Tunnel führt — die Ermittlung des physischen Interfaces unter dem Tunnel, was als Nutzer ohne weitere Root-Rechte nicht möglich ist. Die konservative Regel oben erreicht dasselbe Schutzziel ohne jede dieser drei Voraussetzungen.

**Preis dieser Entscheidung, ausdrücklich benannt:** Sind Ethernet und ein fremdes WLAN gleichzeitig aktiv (typisch an einer Dockingstation), wird nicht gesichert, obwohl es gefahrlos möglich wäre. Abhilfe ist dann, das WLAN abzuschalten. Umgekehrt gilt: Ob über eine erlaubte Verbindung tatsächlich Internet bzw. der Server erreichbar ist, wird nicht eigens geprüft — ein gestarteter Client, der den Server nicht erreicht, wartet einfach, und das ist ungefährlich.

**Ausdrücklich nicht betrachtete Sonderfälle:** Auswertung des tatsächlichen Routings, Namensauflösung der Serveradresse und die Frage, über welches physische Interface ein VPN-Tunnel verläuft. Öffnet der Nutzer selbst ein VPN, entscheidet er selbst, ob er die Sicherung abschaltet; ist der VPN-Zugang seinerseits ein Access Point, greift wieder die Erlaubnisliste. Das ist keine Auslassung, sondern eine Abgrenzung: Diese Fälle sind unüblich und ihre Behandlung würde zusätzliche Root-Rechte verlangen.

## Manuelles Aktivieren und Deaktivieren

Neben der Netz-Erlaubnis gibt es einen **zweiten, davon unabhängigen Zustand**: die manuelle Freigabe durch den Nutzer. Beide werden **verundet** — gesichert wird nur, wenn das Netz passt **und** der Nutzer nicht deaktiviert hat.

- Der Zustand wird bei **jedem Dienststart** auf „aktiviert" gesetzt. „Nicht deaktiviert" ist also der Normalfall, genau wie zum Dienststart.
- Er wird **nicht persistiert** und lebt nur im Speicher des laufenden Dienstes (und als Anzeigefeld im vollständigen Status, siehe `state.json`). Dass ein manuelles „Deaktiviert" spätestens beim nächsten Dienststart verfällt, ist gewollt: Das Werkzeug arbeitet auf Rechnern, die nicht durchlaufen, also spätestens am nächsten Tag wieder anlaufen — und bis dahin erinnern die Zwei-Stunden-Meldungen daran.
- Der manuelle Zustand kann die Netzregel in **keiner** Richtung übergehen. „Aktivieren" heißt nicht „jetzt trotzdem sichern", sondern nur „meinen Einspruch zurückziehen"; ist das Netz nicht erlaubt, bleibt gestoppt. Andernfalls wäre genau die Lücke offen, die dieser Dienst schließen soll.

**Zwei Bedienwege, ein Mechanismus:** Sowohl der Notification-Button als auch das Kommandozeilenwerkzeug schreiben in eine **Kommandodatei unter `/run/urbackup-gated/`**, die der Dienst per inotify beobachtet — dasselbe Verfahren, das für die Netzwerk-Ereigniserkennung ohnehin schon festgelegt ist (siehe „Netzwerk-Ereigniserkennung"). Kein zusätzliches Übertragungsverfahren, und die Wirkung tritt sofort ein statt erst beim nächsten Zeittakt.

**Invariante: absolutes Setzen, kein Umschalten.** Die beiden Befehle lauten „setze auf deaktiviert" bzw. „setze auf aktiviert", niemals „kippe den aktuellen Zustand". Grund: Ein Notification-Aufruf blockiert bis zum Klick oder Timeout, zwischen Anzeige und Klick können Minuten liegen, und in dieser Zeit kann der Zustand über den anderen Bedienweg schon verändert worden sein. Beim absoluten Setzen ist ein solcher verspäteter Klick wirkungsgleich mit einem sofortigen (idempotent); ein Umschalter hingegen würde den zwischenzeitlich gesetzten Zustand unbeabsichtigt kippen.

## Auslösepunkte (Trigger)

1. Dienststart selbst (führt sofort eine volle Netzwerkprüfung durch).
2. Verbindungsauf-/-abbau (event-getrieben, z. B. über NetworkManager-Dispatcher) per Ethernet- oder WLAN-Device. (Auf- und Abbau von VPN-Verbindungen werden nicht überwacht bzw. ausgewertet.)
3. Zeitgesteuert alle 30 Sekunden (Fallback, falls ein Event verpasst wird) — bei
   diesem Trigger und beim Dienststart werden die Netzwerkverbindungen zusätzlich aktiv
   geprüft (nicht nur der zuletzt gemeldete Event-Zustand).
4. Änderung der Kommandodatei, also manuelles Aktivieren oder Deaktivieren durch den Nutzer (siehe „Manuelles Aktivieren und Deaktivieren"). Ebenfalls per inotify erkannt, damit die Bedienung sofort wirkt und nicht bis zum nächsten Zeittakt wartet.

Punkte 2 und 4 sind zwei **getrennte** beobachtete Dateien mit verschiedenen Schreibern — in die eine schreibt der NetworkManager-Dispatcher als root, in die andere der Nutzer über Notification-Button oder Kommandowerkzeug. Der Beobachtungsmechanismus ist derselbe (siehe „Netzwerk-Ereigniserkennung"), die Auslöser sind es nicht.

## Verhalten bei Netzwechsel während laufender Sicherung

Wechselt die WLAN-SSID während des gestarteten UrBackup-Clients ins Verbotene (z. B. Wechsel vom erlaubten Netz zum
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
UrBackup nimmt eine so unterbrochene Sicherung später nach Neustart von selbst wieder auf,
wie wir bei der Fehlersuche am eigentlichen UrBackup-Client mehrfach
beobachtet haben.

**Warum wir gegen häufiges Stoppen und Starten trotzdem keine eigene Entprellung einbauen:** Ein Neustart des Clients ist nicht billig — er scannt zunächst die Dateibestände, was auf diesem Rechner über 20 Minuten dauert. Bei schlechtem Empfang oder ständigem Wechsel zwischen erlaubtem Netz und Hotspot könnte es dadurch nie zu einer wirklichen Sicherung kommen. Eine Mindest-Verweildauer im eigenen Dienst ist dafür aber unnötig: Der UrBackup-Client bringt selbst eine konfigurierbare Startverzögerung mit (auf diesem Rechner 5 Minuten), bevor er überhaupt tätig wird, und fängt das Flattern damit schon ab. Wer mehr Ruhe braucht, erhöht diesen Wert in UrBackup — ohne dass `urbackup-gated` etwas dazu beitragen muss.

## Zustand, Merken zwischen Aufrufen und Statusabfrage

Fester, bekannter Pfad `/run/urbackup-gated/state.json` statt der ursprünglichen
Idee einer UUID-Datei unter `/tmp`. `/run` ist per Definition ein tmpfs und wird
bei jedem Neustart automatisch geleert — das erfüllt genau den gewünschten Zweck
("Datei weg = Ausgangslage klar nach Neustart"), ist aber unter einem festen,
auffindbaren Namen leichter zu debuggen als eine zufällige UUID-Datei.

**Festgelegt:** Dort wird nicht nur der reine Boot-Merker abgelegt, sondern der
**vollständige Status** — erkannte Netzwerklage (alle aktiven Verbindungen mit Typ und, bei WLAN, SSID),
getroffene Entscheidung samt Begründung, sowie der UrBackup-Client-Status
(`urbackupclientctl status`, s. u.). Es gibt dafür genau eine Backend-Funktion
„vollständigen Status ermitteln/aufbereiten", die von drei Stellen verwendet wird:

1. **Der Dienst selbst** — ruft sie bei jedem Trigger (Start, Netzwechsel,
   30-Sekunden-Takt) auf und schreibt das Ergebnis nach `state.json`.
2. **Das Yad-Detailfenster** beim Notify-Klick (s. u.) — ruft dieselbe
   Funktion live neu auf, da es im selben Prozess läuft; kein Umweg über die
   Datei nötig, dadurch tagesaktuellster Stand.
3. **Ein separates Kommandozeilenwerkzeug** (löst die „Testbarkeit"-Frage
   aus dem Konzept) — liest für die Statusanzeige nur `state.json` und zeigt sie lesbar an, ohne
   selbst etwas neu zu ermitteln. Zeigt dabei an, wie lange das letzte Schreiben der Datei her ist. Dadurch höchstens rund 30 Sekunden alt
   (Zeittrigger-Intervall), wenn der Dienst läuft, aber ohne eigene Berechtigungen/Logik-Duplizierung bezüglich des Inhalts, der Bewertung usw.
   Ersetzt die ursprünglich angedachte separate Dry-Run-Logik: Ein eigener
   Entscheidungs-Simulator wäre nötig gewesen, wenn der Dienst selbst befragt
   werden sollte, ohne dass er läuft — da er aber ohnehin läuft, reicht das
   Auslesen seines echten, aktuellen Zustands.

Das Kommandozeilenwerkzeug hat damit **zwei Rollen und entsprechend Unterbefehle**: Status lesen (rein lesend, wie oben beschrieben) sowie manuelles Aktivieren/Deaktivieren (schreibend, über die Kommandodatei — siehe „Manuelles Aktivieren und Deaktivieren"). Auch der schreibende Weg enthält keine eigene Entscheidungslogik: Er setzt nur den Nutzer-Zustand, bewertet wird ausschließlich im Dienst.

Der manuelle Nutzer-Zustand ist Teil des vollständigen Status und wird in `state.json` mitgeführt — sonst könnte weder das Statuswerkzeug noch das Detailfenster anzeigen, warum gerade nicht gesichert wird.

Die eigentliche Ermittlungslogik existiert damit nur ein einziges Mal im Code.

## Notify-Meldungen

- Beim tatsächlichen Starten des UrBackup-Clients.
- Beim tatsächlichen Stoppen des UrBackup-Clients.
- Bei Zustandswechsel "UrBackup-Server verbunden" ↔ "UrBackupserver nicht verbunden" (im laufenden Betrieb erkannt bei den
  Zeittriggern).
- Bei Zustandswechsel "Sicherung läuft nicht" ↔ "Sicherung läuft" (im laufenden Betrieb erkannt bei den
  Zeittriggern).
- Wenn keine Sicherung läuft: alle 2 Stunden (bei einem der Zeittrigger; Zeit konfigurierbar) eine kurze
  Meldung, ob eine Verbindung zum UrBackup-Server besteht. Wird nicht gesichert, nennt diese Meldung
  ausdrücklich den **Grund** — „manuell deaktiviert" gegenüber „Netz nicht erlaubt" gegenüber „keine
  Netzwerkverbindung". Ohne diese Unterscheidung wäre für den Nutzer nicht erkennbar, ob er selbst
  abgeschaltet hat und es nur vergessen hat, oder ob die Netzlage den Betrieb verhindert.
- Wenn eine Sicherung läuft: alle 15 Minuten (konfigurierbar) ein kurzer Fortschrittsstatus.
- Anzeigedauer 5 Sekunden, konfigurierbar.

Datenquelle für Serververbindung/Sicherungsfortschritt: `urbackupclientctl status`
(JSON-Ausgabe). **Geprüft:** Der Aufruf funktioniert mit reinen Benutzerrechten, ohne `sudo`. Das war nicht selbstverständlich und ist tragend für den Entwurf: Der Aufruf erfolgt bei jedem Zeittakt, also alle 30 bzw. 5 Sekunden. Hätte er Root-Rechte gebraucht, wäre eine dritte, sehr häufig genutzte `sudoers`-Freigabe nötig geworden — und die eng gefasste Rechteaufteilung (siehe „Systemintegration und Rechteaufteilung") bliebe bei genau zwei seltenen Befehlen nicht mehr bestehen.

Die relevanten Felder, alle im Quellcode verifiziert
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

Live getestet und bestätigt funktionsfähig: `notify-send -A "default=..." -A "details=..."`
zeigt auf diesem Desktop (KDE/Plasma/X11) tatsächlich einen klickbaren Button, und die
gewählte Aktion kommt als Text auf stdout beim aufrufenden Prozess an — ganz
ohne eigene D-Bus-Anbindung. Klickt man auf „Details", öffnet derselbe
Prozess im Anschluss `yad` mit dem vollständigen
`urbackupclientctl status`. Es gibt keine unabhängige Verbindung zwischen
Notify-Klick und Yad — der aufrufende Prozess blockiert (`--action`
impliziert `--wait`), bekommt die Klick-Antwort direkt zurück und entscheidet
im selben Ablauf, ob er Yad startet.

Konsequenz für die Umsetzung: Da dieser Aufruf blockiert, darf er nicht in
der Haupt-Schleife des Dienstes laufen (sonst steht die 30-Sekunden-Prüfung
still, solange eine Notification unbeantwortet auf dem Bildschirm hängt) —
er muss in einem eigenen Thread/Hintergrundprozess erfolgen.

**Button-Belegung jeder Meldung:** `Details` ist immer vorhanden. Dazu kommt genau einer der beiden Schaltbefehle, abhängig vom aktuellen manuellen Nutzer-Zustand — `deactivate`, solange der Nutzer nicht deaktiviert hat, und `activate`, wenn er deaktiviert hat (siehe „Manuelles Aktivieren und Deaktivieren"). Da die periodischen Meldungen ohnehin regelmäßig erscheinen (bei laufender Sicherung alle 15 Minuten), ist damit auch ohne Kommandozeile jederzeit eine Bedienmöglichkeit vorhanden.

Die ursprüngliche Sorge, ein klickbarer Button könnte die gewünschten 5
Sekunden Anzeigedauer unterlaufen, hat sich als unbegründet erwiesen: Live
beobachtet läuft die Anzeigedauer normal ab; sie pausiert nur, solange der
Mauszeiger über der Notification steht (verbreitetes, gewolltes Verhalten
vieler Notification-Server, kein UrBackup-gated-spezifisches Problem).

### Dauerhaft offenes, live aktualisierendes Statusfenster

**Festgelegt:** Der „Details"-Klick öffnet statt einer einmaligen Momentaufnahme
ein dauerhaft offenes Fenster, das der Nutzer stehen lassen kann und das sich
selbst mit aktuellem Status überschreibt — kein Log, das anwächst.

**Weg dahin, mit den unterwegs verworfenen Alternativen:**

- `zenity --text-info --auto-scroll`: live getestet, **kann nur anhängen,
  nicht überschreiben** — vier verschiedene Steuerzeichen-Versuche (ANSI
  Clear-Screen, Form-Feed, zehnfaches Backspace) blieben ohne jede Wirkung,
  Zeichen wurden entweder verschluckt oder als sichtbarer Text angehängt.
  Damit als Weg verworfen.
- `zenity --progress` mit `#`-Zeilen: **überschreibt** tatsächlich eine
  einzelne Textzeile plus Prozentbalken (live bestätigt) — aber nur eine
  einzelne Zeile, kein mehrzeiliger Statusumfang wie gewünscht. Für unseren
  Zweck nicht ausreichend, damit ebenfalls verworfen.
- **`yad --text-info --listen`** (Fork von Zenity, per `apt install yad`
  nachinstalliert): laut eigenem Handbuch löscht ein Form-Feed-Zeichen
  (`\f`, sendbar als `echo -e '\f'`) den Textinhalt. Live bestätigt — mit
  einer wichtigen, im Quellcode (`yad`, `src/text.c`, `handle_stdin()`)
  gefundenen Einschränkung: `yad` liest zeilenweise; ein `\f` als erstes
  Zeichen einer Zeile löscht den gesamten Puffer, **verwirft aber den Rest
  dieser Zeile vollständig** — Text nach dem `\f` in derselben Zeile geht
  verloren. Der korrekte Ablauf ist deshalb: `\f` als **eigene, vollständige
  Zeile** senden (mit eigenem Zeilenumbruch abgeschlossen), der neue Status
  folgt als **separate** nachfolgende Zeile. So getestet, funktioniert
  zuverlässig.

**Damit ist `yad` eine zusätzliche Laufzeitabhängigkeit** neben `notify-send` (aus `libnotify-bin`). **`zenity` entfällt dafür vollständig:** Auch das einmalige Fail-safe-Fehlerfenster bei kaputter Konfiguration (s. u.) wird mit `yad` gebaut. Damit laufen alle Dialoge über dasselbe Programm, und unter dem Strich ist es eine Abhängigkeit weniger statt einer mehr — `yad` brauchen wir für das Live-Fenster ohnehin, `zenity` könnte danach nur noch Dinge, die `yad` auch kann.

Folge daraus, die beim Programmieren nicht untergehen darf: Weil jetzt **auch die Fehleranzeige** an `yad` hängt, prüft der Dienst bei seinem Start, ob `yad` überhaupt vorhanden ist, und schreibt dessen Fehlen ins Journal. Ohne diese Prüfung fiele im kaputten Zustand ausgerechnet die Meldung darüber aus — der Nutzer sähe gar nichts und hätte keinen Anhaltspunkt.

**Weitere Festlegungen zu diesem Fenster:**

- **Aktualisierungstakt:** im Rahmen der bestehenden 30-Sekunden-Zeitscheibe
  des Dienstes, aber diese Zeitscheibe auf 5 Sekunden verkürzt (konfigurierbar), solange dieses Fenster
  offen ist.
- **Schließen erkennen:** über die fehlschlagende Schreiboperation auf die
  dann geschlossene Pipe (Broken Pipe) — einfachstes, übliches Verfahren,
  kein Rückkanal nötig.
- **Nur ein Fenster gleichzeitig:** Solange dieses Statusfenster offen ist,
  werden die regulären Notify-Meldungen unterdrückt — sie wären redundant,
  der Status ist ja im offenen Fenster einsehbar.

**Kein eigener Test nötig, wird beim ersten Lauf des echten Dienstes mitverifiziert:** Alle `yad`-Tests liefen interaktiv im Terminal, nicht aus einem `systemd --user`-Dienst heraus. Ein eigener Testaufbau dafür (analog zum früheren `urbackup-gated-test.service`) ist trotzdem nicht erforderlich, denn was der damalige Zenity-Test bewiesen hat, ist keine Eigenschaft des Dialogprogramms, sondern **der Sitzung**: dass der `systemd --user`-Manager `DISPLAY`/`WAYLAND_DISPLAY`/`XAUTHORITY`/`DBUS_SESSION_BUS_ADDRESS` an seine Kinder weitergibt. Welches Programm damit anschließend den Anzeigeserver anspricht, ändert an dieser Weitergabe nichts.

Der Vollständigkeit halber die Einschränkung dieses Schlusses: `yad` und `zenity` sind auf diesem Rechner **nicht derselbe Bibliotheksstand** — `ldd` zeigt `yad` gegen `libgtk-3`, `zenity` gegen `libgtk-4` (beobachtet, nicht aus der Dokumentation). Das entkräftet die Argumentation nicht, weil beide GTK-Generationen dieselben Umgebungsvariablen auswerten; es heißt nur, dass hier nicht „identische Bibliothek, also bewiesen" behauptet wird.

Der `--listen`-Teil ist ohnehin keine systemd-Frage: Der Dienst bekommt von systemd `/dev/null` auf seinem eigenen stdin, aber `yad` erhält seine Pipe nicht von dort, sondern von dem Subprozessaufruf, mit dem `urbackup-gated` es selbst startet. Diese Pipe kontrollieren wir vollständig.

## Konfiguration

Eigene Datei/Ordner: `/etc/urbackup-gated` (wenn es bei einer Datei bleibt, reicht die Konfigurationsdatei `/etc/urbackup-gated.conf`, andernfalls kommen die Files in einen Ordner `/etc/urbackup-gated`). Muss mindestens enthalten: Liste
erlaubter SSIDs, konfigurierbare Zeiten / Intervalle, soweit sie einstellbar sein sollen statt fest im Code.

Aktuell genannte SSIDs: `lieluX`, `lielux`, `lieluxVPN`, `HZDR` — geklärt: kein
Tippfehler, `lieluX` und `lielux` sind zwei tatsächlich unterschiedliche, echte
Netze. Vergleich bleibt case-sensitiv. Diese SSIDs werden schon im Repo als Beispiel so benutzt.

### Fail-safe bei fehlender/kaputter Konfiguration

Fehlt `/etc/urbackup-gated` als Ordner bzw. Konfigurationsdatei, ist sie nicht lesbar oder inhaltlich fehlerhaft
(z. B. keine gültige SSID-Liste), bleibt `urbackupclientbackend` **gestoppt**
bzw. wird gestoppt — unabhängig davon, welches Netz gerade aktiv ist. Sicherer
Default: eine verpasste Sicherungsgelegenheit ist unkritisch, eine ungeprüft
laufende Sicherung über ein möglicherweise nicht erlaubtes Netz wäre genau
das Risiko, das der Dienst verhindern soll.

Keine eigene Notify-Meldung für diesen Fall — der Nutzer erkennt den
Fehlzustand indirekt am Ausbleiben der gewohnten Verbindungs-/
Sicherungsmeldungen. Stattdessen ein **Yad-Fehlerfenster** mit der
konkreten Fehlerursache, das per Klick auf „OK" quittiert werden muss. Damit
weiß der Nutzer gezielt, was kaputt ist, und kann `urbackupclientbackend` im
Zweifel manuell starten, statt nur zu bemerken, dass „nichts mehr kommt".

## Protokollierung

Festgelegt: normale Ausgabe auf stdout/stderr, kein eigenes Logfile. Landet
dadurch automatisch im systemd-Journal (`journalctl --user -u urbackup-gated`)
und braucht keine eigene Rotation/Aufräumlogik. Fehleranzeige bei `systemctl --user status urbackup-gated` — mit `--user`, da es ein Dienst der Nutzersitzung ist und der Befehl ohne diese Option den System-Manager abfragen würde, der die Unit gar nicht kennt.

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

Abgefragt wird nicht die primäre Verbindung, sondern **die vollständige Liste aller aktiven Verbindungen**, je Eintrag mit Typ (Ethernet/WLAN/sonstiges) und, bei WLAN, der SSID. Das folgt zwingend aus den Entscheidungsregeln: Eine einzige aktive, nicht erlaubte WLAN-Verbindung verbietet den Betrieb, auch wenn sie nicht die primäre Verbindung ist. Eine Abfrage, die nur die primäre Verbindung liefert, wäre für diese Regel unbrauchbar.

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
