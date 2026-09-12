# Zusammenhänge

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
`urbackup-gated.service`, Konfigurationsdatei `/etc/urbackup-gated.conf`.

## Systemintegration und Rechteaufteilung

`urbackup-gated` läuft als `systemd --user`-Dienst, nicht als System-Dienst.
Desktop-Notifications laufen dadurch ganz natürlich in der eigenen Sitzung, ohne
Umweg über eine fremde D-Bus-Session.

**Genauer: Er gehört zur grafischen Sitzung, nicht zur Anmeldung überhaupt.** Die Unit hängt in beide Richtungen an `graphical-session.target` — sie startet mit ihr und endet mit ihr. Das ist nicht dasselbe wie `default.target`: Dieses Ziel wird bei **jeder** Anmeldung erreicht, auch bei einer reinen SSH-Sitzung, und in der Regel bevor der Desktop `DISPLAY`, `WAYLAND_DISPLAY` und `XAUTHORITY` an den User-Manager übergeben hat. Ein Dienst, der dort startet, könnte für die ganze Sitzung ohne Anzeige laufen: Statusfenster und Fehlerdialog blieben stumm.

**Der tragende Grund ist aber nicht die Anzeige, sondern die Bedienbarkeit:** Nur in einer grafischen Sitzung kann der Nutzer das Netz überhaupt auswählen. Vor der Anmeldung könnte das System selbstständig einen limitierten Zugang aufbauen — und niemand wäre da, um einzugreifen. Die Regel „Sicherung läuft nur, wenn angemeldet" wird damit zu „nur, wenn jemand am Rechner sitzt und handeln kann".

**Benannte Folge:** Auf einem Rechner, an dem sich jemand ausschließlich per SSH anmeldet, läuft der Dienst nicht — dort wird weder gegatet noch gemeldet.

`urbackupclientbackend.service` bleibt ein System-Dienst mit Root-Rechten
(unverändert). Damit `urbackup-gated` ihn dennoch steuern kann, ohne selbst Root
zu sein, bekommt es über `sudoers` eine eng gefasste, passwortlose Freigabe für
genau drei Befehle, jeweils mit absolutem Pfad `/usr/bin/systemctl` und ohne
Platzhalter: `start`, `stop` und `disable`, jedes Mal auf
`urbackupclientbackend.service` — keine weiteren Rechte. Der dritte Eintrag ist
nicht optional: Ohne ihn kann die weiter unten beschriebene Selbstheilung nach
einer UrBackup-Neuinstallation nicht funktionieren, weil `systemctl disable`
ebenfalls Root-Rechte verlangt. Die reinen Abfragen `is-active` und `is-enabled`
sind lesend, brauchen kein `sudo` und stehen deshalb **nicht** in der Freigabe.

**Ablageort der Freigabe:** eine eigene Datei in `/etc/sudoers.d/`, nicht ein
Eingriff in `/etc/sudoers` selbst — so kann `install.sh` sie anlegen und
`uninstall.sh` sie restlos entfernen, ohne je an einer fremden Datei zu
schneiden. Drei Eigenschaften sind dabei zwingend, weil sie sonst je genau
einmal schmerzhaft auffallen:

- Der Dateiname darf **keinen Punkt** enthalten, sonst wird die Datei
  kommentarlos ignoriert. Also `urbackup-gated`, nicht `urbackup-gated.conf`.
- Eigentümer `root:root`, Modus `0440`.
- `install.sh` schreibt zuerst in eine Temporärdatei, prüft sie mit
  **`visudo -c -f`** und schiebt sie erst bei Erfolg an ihren Platz. Eine
  fehlerhafte sudoers-Datei sperrt `sudo` systemweit aus — das ist der einzige
  Fehler in diesem Vorhaben, der wirklich teuer wäre.

`urbackupclientbackend.service` wird aus dem automatischen Systemstart genommen
(`systemctl disable`, nicht `mask`), damit es nicht schon vor der Anmeldung mit
Root-Rechten hochkommt. Im laufenden Betrieb ist `urbackup-gated` die einzige
Instanz, die den Client startet oder stoppt.

**Mit einer Ausnahme, die zur Einrichtung gehört:** `install.sh` stoppt ihn
selbst, und zwar mit `disable --now` im selben Zug, in dem es ihn aus dem
Systemstart nimmt. Läuft zu diesem Zeitpunkt eine Sicherung, wird auch sie
beendet. Das ist richtig so — der Client soll ab dann nicht mehr ungeprüft
laufen, und ein Zustand „noch aus der Zeit vor der Installation" wäre genau der,
den niemand beurteilt hat. Es gehört aber gesagt, damit es nicht als Verstoß
gegen den Satz davor gelesen wird.

**Ein unbeantwortbarer Unit-Zustand zählt als „läuft".** `systemctl` spricht über D-Bus mit dem System-Manager und kann dort hängen — unter Last oder während der Anmeldephase. Eine solche Abfrage liefert deshalb nicht „ja" oder „nein", sondern einen dritten Wert: **unbekannt**. Gehandelt wird darauf, als liefe der Client. Das ist die einzige Richtung, die in beiden Zweigen trägt: Ist das Netz verboten, wird ein Stopp wenigstens **versucht**; ist es erlaubt, wird lediglich **nicht gestartet**. Die umgekehrte Annahme hätte den gefährlichen Ausgang — ein laufender Client über einem volumenbeschränkten Netz, den niemand anhält. Es ist dieselbe Regel wie bei der Netzlage, nur auf den Client angewandt: Eine verpasste Sicherungsgelegenheit ist unkritisch, eine ungeprüfte Sicherung nicht.

**Die Rücknahme gehört zur Festlegung:** `uninstall.sh` nimmt den Client-Dienst wieder in den Systemstart auf (`systemctl enable --now`). Sonst bliebe nach dem Entfernen von `urbackup-gated` ein deaktivierter Client zurück, den niemand mehr startet — das Ergebnis wäre „gar keine Sicherungen mehr", und zwar unbemerkt, weil auch die Meldungen mit dem Dienst verschwinden. Die Deaktivierung ist also kein Zustand, den wir herstellen, sondern einer, den wir für die Dauer unserer Zuständigkeit halten. Gelingt das Wiederaktivieren nicht, sagt `uninstall.sh` das ausdrücklich, statt es zu verschweigen. Die Konfigurationsdatei bleibt dabei absichtlich stehen; sie zu löschen ist Sache des Nutzers.

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

## Installation und Deinstallation

### Ordnerstruktur des Repositorys

Fünf Orte, jeder mit genau einer Aufgabe:

| Ort | Aufgabe |
|---|---|
| `src/urbackup_gated/` | Das Programm. Es weiß nicht, wohin es installiert wird — wohl aber, wo es zur Laufzeit liest und schreibt. |
| `packaging/` | Dateien, die unverändert oder mit Platzhalterersetzung an einen festen Ort im System gelangen und nicht Python sind: systemd-Unit, Dispatcher-Hook, `tmpfiles.d`-Schnipsel, `sudoers`-Freigabe, Vorgabekonfiguration, Anwenderdokumentation. |
| `tests/` | Die Prüfung, Stufe 1 und 2, samt Attrappen und Szenarien. |
| `running_implementation_doc/` | Diese Dokumentation, Fahrplan und Status. |
| `install.sh`, `uninstall.sh` in der Wurzel | Der Einstiegspunkt. Sie stehen dort, weil sie das Erste sind, was ein Nutzer nach dem Klonen sucht. |

**Nicht** Aufgabe von `packaging/`: der Installer selbst, Bauvorschriften, Testattrappen, **Projekt**dokumentation — also diese Implementierungsdoku und die Projekt-README in der Wurzel.

**Die Anwenderdokumentation gehört dagegen sehr wohl dorthin** (`packaging/doc/README.md`), und zwar nach derselben Definition wie alles andere in diesem Ordner: Sie gelangt unverändert an einen festen Ort im System (`/usr/local/share/doc/urbackup-gated/`). Sie lag bis zum 12. September 2026 in der Wurzel und wurde von dort installiert — ein Paketbestandteil außerhalb des Paketordners. Damit hängt eine zweite Festlegung zusammen: **Projekt-README und Anwenderdokumentation sind zwei Dokumente mit zwei Aufgaben.** Die Projekt-README ist die Eingangsseite — wofür ist das gut, wie sieht es aus, wie bekommt man es, wie ist das Repository gebaut. Die Anwenderdokumentation trägt die Einzelheiten zu Installation, Bedienung und Konfiguration. Keine Aussage steht in beiden; die Eingangsseite verweist auf die andere, statt sie zu wiederholen.

**Zu `src/`:** Das ist hier ein Ordnername und **kein Distributionsversprechen**. Es gibt bewusst keine `pyproject.toml`, weil dies ein in Python geschriebener **Dienst** ist und keine Bibliothek — nichts daran soll je importierbar veröffentlicht werden. Eine Recherche zu vergleichbaren Vorhaben hat ergeben, dass es für Dienst-Projekte **keine etablierte Konvention** gibt: Vier untersuchte Python-Dienste mit Systemintegration benutzen vier verschiedene Layouts, uneinig schon über den Ort des Quellcodes. Was es normativ gibt, sind Paketierungsregeln der Distributionen — die regeln, wie eine Distribution fremde Software verpackt, nicht wie deren Repository aussieht.

### Die Ableitungsregel

**Jede Datei unter `packaging/` hat genau ein Ziel im System.** `install.sh` ist die einzige Stelle, die diese Zuordnung kennt. Sie wird nicht ein zweites Mal aufgeschrieben — auch nicht in `uninstall.sh`, was bis zuletzt der Fall war: Zwei Listen derselben Pfade bedeuten, dass ein neu hinzugekommener Pfad irgendwann nur in einer von beiden steht, und die Deinstallation dann still eine Datei zurücklässt.

Stattdessen schreibt `install.sh` ein **Manifest** dessen, was es abgelegt hat, und `uninstall.sh` arbeitet ausschließlich daraus. Im Manifest steht außerdem der Dienstnutzer, damit die Deinstallation ihn nicht raten muss — wer entfernt, muss nicht derselbe sein, für den installiert wurde. Fehlt das Manifest, bricht `uninstall.sh` ab und sagt warum; ein Rückfall auf eine eingebaute Liste wäre genau die Doppelpflege, die hier beseitigt werden soll.

Nicht im Manifest steht die **Konfigurationsdatei**: Sie soll die Deinstallation überleben, ist also nichts zu Entfernendes. Ebenso wenig das Wiederaktivieren des Client-Dienstes — das ist eine Handlung, keine Datei (siehe „Die Rücknahme gehört zur Festlegung" weiter oben).

### Der Installationsweg

Repository klonen, `install.sh` als root ausführen, fertig. **Der Klon ist danach entbehrlich** — es wird alles kopiert, nichts verlinkt. Genau deshalb gehören auch der Deinstaller und die Anwenderdokumentation ins System: Wer den Klon wegwirft, was nach dem übrigen Entwurf naheliegt, stünde sonst ohne Weg zurück und ohne Dokumentation da.

| Was | Wohin |
|---|---|
| Python-Paket | `/usr/local/lib/urbackup-gated/urbackup_gated/` |
| Manifest | `/usr/local/lib/urbackup-gated/manifest` |
| Dienst und Kommandowerkzeug | `/usr/local/bin/urbackup-gated`, `…-ctl` |
| Deinstaller | `/usr/local/bin/urbackup-gated-uninstall` |
| Anwenderdokumentation | `/usr/local/share/doc/urbackup-gated/` |
| systemd-User-Unit | `/usr/local/lib/systemd/user/` |
| `tmpfiles.d`-Schnipsel, `sudoers`-Freigabe, Dispatcher-Hook, Konfiguration | an ihren jeweiligen Systemorten unter `/etc` |

### Der Dienst läuft auf dem System-Python

**Festgelegt: `/usr/bin/python3`, und nicht das, was gerade im Suchpfad steht.** Ein virtuelles Environment gehört einem Nutzer und einer Aufgabe — es wird im Laufe einer Sitzung gewechselt, und auf manchen Rechnern gibt es mehrere davon nebeneinander. Der Dienst muss über all das hinweg weiterlaufen. Er darf seinen Interpreter deshalb nicht aus dem Suchpfad beziehen.

**Was das praktisch heißt:** Die per `apt` installierten Module liegen in `/usr/lib/python3/dist-packages`; dieses Verzeichnis steht nur im Suchpfad des System-Interpreters, nicht in dem eines virtuellen Environments. Am Zielrechner nachgemessen: Dort fand das aktive Environment `watchdog` nicht, obwohl das Paket installiert war.

**Geprüft wird derselbe Interpreter, der später läuft.** Das ist der eigentliche Punkt — es ist keine Übereinstimmung, die man einhalten muss, sondern eine, die nicht brechen kann: Beide Seiten, die Abhängigkeitsprüfung im Installer und der erzeugte Startbefehl, stammen aus **einer** Stelle. Vorher fragte die Prüfung den Suchpfad und der Startbefehl nannte den festen Pfad; dass das auf dem Zielrechner trotzdem zusammenpasste, lag allein daran, dass `sudo` den Suchpfad zurücksetzt — also an der Umgebung, nicht am Skript.

**Der Pfad ist Konvention, die Eigenschaft ist die Bedingung.** Eine Umgebungsvariable, die „das System-Python" benennt, gibt es nicht — weder in POSIX noch bei Debian oder Ubuntu. Was es gibt: Auf diesen Distributionen gehört `/usr/bin/python3` einem `apt`-Paket und trägt seit Ubuntu 23.04 die PEP-668-Markierung `EXTERNALLY-MANAGED`, also „wird von der Distribution gepflegt, nicht von `pip`". Der Installer verlässt sich aber nicht darauf, sondern **prüft die Eigenschaft nach**: Ein Interpreter weiß selbst, ob er in einem virtuellen Environment steckt (`sys.prefix` gegenüber `sys.base_prefix`). Steht dort eines, bricht die Installation mit dieser Begründung ab. Damit trägt die Festlegung auch dann, wenn eine künftige Distribution den Ort anders belegt.

**Warum die Unit unter `/usr/local/lib/systemd/user` und nicht unter `/etc/systemd/user`:** `/etc/systemd/…` ist der Ort für Anpassungen des Administrators; mitgelieferte Units gehören nicht dorthin. Da die Software unter `/usr/local` liegt, ist `/usr/local/lib/systemd/user` der passende Ort — am System als Suchpfad nachgewiesen.

Dass dies eine Installation für **genau einen Nutzer** ist, steht mit Begründung unter „Benannte Nebenwirkung" im Kapitel „Zustand, Merken zwischen Aufrufen und Statusabfrage".

### Die Konfigurationsdatei trägt eine Kurzanleitung

Ihr Kommentarkopf nennt in wenigen Zeilen, was der Dienst tut, wo die vollständige Dokumentation liegt, wie man ihn wieder los wird und was dabei mit dem UrBackup-Dienst geschieht. Grund: Sie ist das Einzige, was der Nutzer nach Monaten sicher wiederfindet — sie liegt an einem festen Ort, und er hat sie selbst bearbeitet.

## Entscheidungsregeln

Bewertet werden **alle gleichzeitig aktiven physischen Verbindungen**, nicht nur eine ausgewählte:

- Irgendeine aktive WLAN-Verbindung, deren SSID **nicht** auf der Erlaubnisliste steht → verboten. Läuft der UrBackup-Client, wird er gestoppt; läuft er nicht, wird er nicht gestartet. Das gilt auch dann, wenn parallel eine Ethernet-Verbindung besteht.
- Sonst, sofern mindestens eine aktive Verbindung vorhanden ist (Ethernet, oder WLAN mit erlaubter SSID) → erlaubt. Läuft der Client nicht, wird er gestartet; läuft er, läuft er weiter.
- Gar keine aktive Netzwerkverbindung → **keine** Entscheidung, der Client bleibt in seinem aktuellen Zustand: gestoppt oder laufend.
- **Die Netzlage lässt sich nicht ermitteln** — `nmcli` fehlt, antwortet nicht oder schlägt fehl → **verboten**, behandelt wie ein nicht erlaubtes Netz. Der Unterschied zum Fall darüber ist wesentlich: „Keine Verbindung" ist eine Feststellung, „unbekannt" ist keine. Über eine Verbindung, die wir nicht beurteilen können, wird nicht gesichert — dieselbe konservative Richtung wie bei kaputter Konfiguration, und aus demselben Grund: Eine verpasste Sicherungsgelegenheit ist unkritisch, eine ungeprüfte Sicherung über ein womöglich volumenbeschränktes Netz ist genau das Risiko, das dieser Dienst ausschließen soll. Der Grund erscheint als solcher im Status und in der Meldung, damit der Nutzer den Fall von einem echten Netzverbot unterscheiden kann.

Die so ermittelte Erlaubnis ist nur die eine Hälfte; sie wird mit dem manuellen Nutzer-Zustand verundet (siehe „Manuelles Aktivieren und Deaktivieren").

**Warum diese bewusst strenge Form, und was sie ersetzt:** Das eigentliche Risiko ist, dass die Verbindung zum Server über eine volumenbeschränkte WLAN-Verbindung läuft, obwohl parallel ein unbeschränkter Kanal online ist — Routing-Entscheidungen sind von außen nicht zuverlässig vorhersagbar. Der naheliegende Weg wäre, per Routing-Abfrage zu ermitteln, über welches Interface der konfigurierte UrBackup-Server tatsächlich erreicht wird. Dieser Weg ist verworfen: Er verlangt die Serveradresse, deren Namensauflösung und — sobald der Weg durch einen Tunnel führt — die Ermittlung des physischen Interfaces unter dem Tunnel, was als Nutzer ohne weitere Root-Rechte nicht möglich ist. Die konservative Regel oben erreicht dasselbe Schutzziel ohne jede dieser drei Voraussetzungen.

**Preis dieser Entscheidung, ausdrücklich benannt:** Sind Ethernet und ein fremdes WLAN gleichzeitig aktiv (typisch an einer Dockingstation), wird nicht gesichert, obwohl es gefahrlos möglich wäre. Abhilfe ist dann, das WLAN abzuschalten. Umgekehrt gilt: Ob über eine erlaubte Verbindung tatsächlich Internet bzw. der Server erreichbar ist, wird nicht eigens geprüft — ein gestarteter Client, der den Server nicht erreicht, wartet einfach, und das ist ungefährlich.

**Ausdrücklich nicht betrachtete Sonderfälle:** Auswertung des tatsächlichen Routings, Namensauflösung der Serveradresse und die Frage, über welches physische Interface ein VPN-Tunnel verläuft. Öffnet der Nutzer selbst ein VPN, entscheidet er selbst, ob er die Sicherung abschaltet; ist der VPN-Zugang seinerseits ein Access Point, greift wieder die Erlaubnisliste. Das ist keine Auslassung, sondern eine Abgrenzung: Diese Fälle sind unüblich und ihre Behandlung würde zusätzliche Root-Rechte verlangen.

## Manuelles Aktivieren und Deaktivieren

Neben der Netz-Erlaubnis gibt es einen **zweiten, davon unabhängigen Zustand**: die manuelle Freigabe durch den Nutzer. Beide werden **verundet** — gesichert wird nur, wenn das Netz passt **und** der Nutzer nicht deaktiviert hat.

- Der Zustand wird bei **jedem Dienststart** auf „aktiviert" gesetzt. „Nicht deaktiviert" ist also der Normalfall, genau wie zum Dienststart.
- Er wird **nicht dauerhaft gespeichert**: Er lebt in einer Datei unter `/run` (Protokoll s. u.), die beim Neustart mit dem tmpfs verschwindet und die der Dienst zusätzlich bei jedem eigenen Start löscht. Dass ein manuelles „Deaktiviert" spätestens beim nächsten Dienststart verfällt, ist gewollt: Das Werkzeug arbeitet auf Rechnern, die nicht durchlaufen, also spätestens am nächsten Tag wieder anlaufen — und bis dahin erinnern die Zwei-Stunden-Meldungen daran.
- Der manuelle Zustand kann die Netzregel in **keiner** Richtung übergehen. „Aktivieren" heißt nicht „jetzt trotzdem sichern", sondern nur „meinen Einspruch zurückziehen"; ist das Netz nicht erlaubt, bleibt gestoppt. Andernfalls wäre genau die Lücke offen, die dieser Dienst schließen soll.

**Zwei Bedienwege, ein Mechanismus:** Sowohl der Notification-Button als auch das Kommandozeilenwerkzeug schreiben in eine **Kommandodatei unter `/run/urbackup-gated/`**, die der Dienst per inotify beobachtet — dasselbe Verfahren, das für die Netzwerk-Ereigniserkennung ohnehin schon festgelegt ist (siehe „Netzwerk-Ereigniserkennung"). Kein zusätzliches Übertragungsverfahren, und die Wirkung tritt sofort ein statt erst beim nächsten Zeittakt.

**Protokoll dieser Datei — eine Zustandsdatei, keine Befehlsliste.** Weil „absolutes Setzen, kein Umschalten" (s. u.) ohnehin gilt, braucht es keine Warteschlange und keine Befehle: Es genügt der gewünschte Zustand, und der letzte Schreiber gewinnt. Ein verlorener Zwischenschritt ist bedeutungslos, weil nur der Endzustand zählt. Das ist der Grund, warum dieser Teil so einfach ausfallen darf.

- Datei `/run/urbackup-gated/user-enabled`, Inhalt genau ein Wort: `enabled` oder `disabled`. Lesbar und notfalls von Hand mit `echo` zu setzen.
- Geschrieben wird **atomar**: erst in eine Temporärdatei im selben Verzeichnis, dann `rename`. Ein Umbenennen innerhalb eines Dateisystems ist unteilbar, der Leser sieht also nie einen halben Inhalt.
- **Fehlende Datei bedeutet `enabled`.** Damit ergibt sich die Regel „bei jedem Dienststart aktiviert" von selbst: Der Dienst löscht die Datei bei seinem Start, und das Zurücksetzen ist im Dateisystem sichtbar statt nur im Speicher.
- Unlesbarer oder unsinniger Inhalt gilt als `disabled`, mit Eintrag ins Journal — dieselbe konservative Richtung wie bei kaputter Konfiguration.
- Der Dienst liest die Datei **bei jeder Bewertung** neu, nicht nur beim inotify-Ereignis. Ein verpasstes Ereignis heilt damit spätestens beim nächsten Zeittakt aus; inotify sorgt allein für die kurze Reaktionszeit, nicht für die Richtigkeit.

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

**Warum nicht `/tmp`, obwohl es näher liegt:** Erstens ist dort das Leeren beim
Neustart **nicht zugesichert**, sondern Konfigurationssache — je nach Distribution
und Version liegt `/tmp` auf der Platte und wird nur von einem Aufräumdienst nach
Alter geleert. Bei `/run` ist die tmpfs-Eigenschaft dagegen definiert und keine
Annahme. Zweitens, und das gibt den Ausschlag: `/tmp` ist für alle schreibbar. Die
Kommandodatei (s. „Manuelles Aktivieren und Deaktivieren") ist ein **Steuerkanal**
— wer hineinschreibt, schaltet die Sicherung ab. Ein vorhersagbarer Name in einem
weltweit schreibbaren Verzeichnis heißt, dass jeder lokale Prozess diesen Kanal
bedienen oder die Datei vorbelegen kann, und wegen des Sticky-Bits könnten wir
eine fremde Datei dort nicht einmal ersetzen. Der Schaden bliebe begrenzt — die
Netzregel gilt weiter und ist nicht übergehbar, es bliebe also bei „Sicherung
lahmgelegt" —, aber der Ausschluss kostet uns nichts.

**Anlegen des Verzeichnisses:** Ein `--user`-Dienst kann in `/run` selbst kein
Verzeichnis erstellen, denn `/run` gehört root und ist `drwxr-xr-x` (am System
nachgesehen). `install.sh` installiert deshalb einen `tmpfiles.d`-Schnipsel, der
`/run/urbackup-gated` bei jedem Neustart mit dem Nutzer des Dienstes als
Eigentümer und Modus `0755` anlegt. Damit darf nur dieser Nutzer — und root, also
der NetworkManager-Dispatcher — dort Dateien anlegen, während Lesen für alle
möglich bleibt, was für die Statusanzeige praktisch ist. Der Dispatcher schreibt
dadurch auf einen festen Pfad und muss keine UID ermitteln; genau deshalb ist
`$XDG_RUNTIME_DIR` (`/run/user/<uid>/`) nicht gewählt, obwohl systemd ein solches
Verzeichnis per `RuntimeDirectory=` von selbst anlegen und aufräumen würde.

**Benannte Nebenwirkung:** Das ist eine Installation für genau **einen** Nutzer.
Für dieses Vorhaben ist das richtig; für einen Mehrbenutzerrechner wäre es zu
wenig gedacht.

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

**Über einen Client, den wir selbst gestoppt haben, sagt die Anzeige nichts.** Ist die Unit nachweislich nicht aktiv, trägt die Client-Detailzeile ein `-` statt einer Diagnose über die Erreichbarkeit des Backends. Grund: Ein gestoppter Client kann nicht antworten — das als „nicht erreichbar (Backend läuft nicht?)" auszugeben, kleidet die eigene Handlung in einen Befund und liest sich wie ein Fehler. In den beiden anderen Lagen bleibt die Diagnose stehen, jede aus eigenem Grund: Läuft die Unit und schweigt das Backend trotzdem, ist das die einzige wirklich auffällige Aussage der ganzen Ausgabe. Und ließ sich der Zustand der Unit nicht einmal ermitteln, ist die Diagnose die beste verbleibende Aussage — ein `-` würde dort eine Gewissheit behaupten, die es nicht gibt. Die Regel gilt für beide Anzeigewege zugleich, weil beide dieselbe Aufbereitungsfunktion benutzen.

### Schema von `state.json`

**Festgelegt:** `schema_version` — damit das Statuswerkzeug eine Datei, die es nicht versteht, ablehnen kann, statt sie falsch anzuzeigen. `written_at` als ISO-8601-Zeitstempel **mit Zeitzone**; daraus berechnet das Statuswerkzeug das geforderte Alter der Angabe. `network` mit der Liste aller aktiven Verbindungen (Typ, Name, bei WLAN die SSID samt Kennzeichen „erlaubt") plus den abgeleiteten Wahrheitswerten „überhaupt eine Verbindung vorhanden" und „nicht erlaubtes WLAN aktiv". `decision` mit den drei getrennten Wahrheitswerten `network_allows`, `user_enabled` und dem verundeten `effective`, dazu `reason` als fertigem, menschenlesbarem Satz. `urbackup_client` mit Unit-Zustand, Serververbindung, laufender Sicherung und den Fortschrittsfeldern.

**Wichtigster Entwurfspunkt darin ist `decision.reason`:** Der Begründungstext entsteht **einmal** in der Sammelfunktion und wird von Notification, Statusfenster und Kommandozeilenwerkzeug gleichermaßen verwendet. Sonst entstehen drei Stellen, die dasselbe in leicht verschiedenen Worten sagen und mit der Zeit auseinanderlaufen.

Geschrieben wird die Datei atomar wie die Kommandodatei (siehe „Manuelles Aktivieren und Deaktivieren").

## Notify-Meldungen

- Beim tatsächlichen Starten des UrBackup-Clients.
- Beim tatsächlichen Stoppen des UrBackup-Clients.
- Bei Zustandswechsel "UrBackup-Server verbunden" ↔ "UrBackupserver nicht verbunden" (im laufenden Betrieb erkannt bei den
  Zeittriggern).
- Bei Zustandswechsel "Sicherung läuft nicht" ↔ "Sicherung läuft" (im laufenden Betrieb erkannt bei den
  Zeittriggern).
- Wenn keine Sicherung läuft: alle 2 Stunden (bei einem der Zeittrigger; Zeit konfigurierbar) eine kurze
  Meldung. Deren Inhalt hängt davon ab, **warum** nicht gesichert wird:
  - Ist die Sicherung erlaubt und der Client läuft, steht dort, **ob eine Verbindung zum UrBackup-Server
    besteht** — die einzige Frage, die dann noch offen ist.
  - Ist sie nicht erlaubt, steht dort stattdessen ausdrücklich der **Grund** — „manuell deaktiviert"
    gegenüber „Netz nicht erlaubt" gegenüber „keine Netzwerkverbindung" gegenüber „Netzlage unbekannt".
    Die Serververbindung wird in diesem Fall **nicht** genannt: Der Client ist gestoppt, es gibt keine.
    Ohne die Unterscheidung der Gründe wäre für den Nutzer nicht erkennbar, ob er selbst abgeschaltet
    und es nur vergessen hat, oder ob die Netzlage den Betrieb verhindert.
- Wenn eine Sicherung läuft: alle 15 Minuten (konfigurierbar) ein kurzer Fortschrittsstatus.
- Anzeigedauer 5 Sekunden, konfigurierbar.

**Jede abgesetzte Meldung setzt beide Abstände zurück** — den der Ruhemeldung wie den der Fortschrittsmeldung. Würde nur der gerade fällige Zähler fortgeschrieben, liefe der andere während der ganzen Zeit weiter: Nach einer Sicherung, die länger als zwei Stunden dauert, käme die Ruhemeldung unmittelbar hinter der Meldung, dass die Sicherung beendet ist. Dasselbe nach dem Schließen des Statusfensters, während dessen gar nichts gesendet wurde. Eine zurückgehaltene Meldung setzt nichts zurück, denn gesagt wurde nichts.

**Eine zurückgehaltene Meldung gilt nicht als erledigt.** Ein `notify-send`-Aufruf mit Schaltflächen blockiert bis zum Klick oder bis der Notification-Server die Meldung schließt; solange geht keine zweite hinaus. Wird ein Zustandswechsel deshalb zurückgehalten, bleibt der gemerkte Vorzustand **stehen**, sodass derselbe Wechsel beim nächsten Takt erneut versucht wird. Andernfalls wäre er nicht verspätet, sondern endgültig verloren — und niemand erführe davon. Der Verwurf selbst geht ins Journal.

**Davon ausgenommen ist das offene Statusfenster.** Dort ist die Unterdrückung gewollt, weil der Status ohnehin sichtbar ist; würde auch hier zurückgehalten, käme nach dem Schließen ein Schwall veralteter Meldungen.

**Ein dritter Zustand, der keinen Wechsel auslöst:** Antwortet `urbackupclientctl status` nicht verwertbar — der Regelfall, sobald der Client-Dienst gestoppt ist —, sind Serververbindung und Sicherungslauf nicht „nein", sondern **unbekannt**. Unbekannt ist keiner der beiden Zustände, zwischen denen die obigen Wechselmeldungen unterscheiden; der Übergang in ihn hinein und aus ihm heraus wird deshalb nicht gemeldet. Ohne diese Festlegung folgt auf jeden netzbedingten Stopp im nächsten Takt eine Meldung über einen Serververlust, den es nicht gab — der Dienst hat den Client ja selbst angehalten. Der Preis ist ausdrücklich benannt: Nach einem Start des Clients entfällt die Folgemeldung „Server verbunden"; dass der Client gestartet wurde, steht bereits in der Meldung desselben Takts, und bleibt der Server unerreichbar, nennt das die Ruhemeldung.

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

**Zweite Folge, den Installer betreffend:** `yad` ist auf einem Desktop in der Regel **nicht** vorinstalliert, `notify-send` oft ebenso wenig. Beide abzulehnen und den Nutzer wegzuschicken wäre die schlechteste Lösung — also erkennt `install.sh` das fehlende Programm, benennt das Paket und **bietet die Nachinstallation an**. Zusätzliche Rechte braucht es dafür nicht: Der Installer läuft ohnehin nur als root, eingeholt wird also nicht ein Recht, sondern die Einwilligung, ein weiteres Paket auf den Rechner zu bringen. Lehnt der Nutzer ab, bricht der Installer ab — und zwar an einer Stelle, an der noch nichts abgelegt wurde, sodass kein halb eingerichteter Zustand zurückbleibt. Für unbeaufsichtigte Läufe beantwortet ein Schalter `--yes` die Frage vorweg. NetworkManager ist bewusst **nicht** in dieser Behandlung: Fehlt er, fehlt die Grundlage des ganzen Werkzeugs, und das ist eine Entscheidung über den Rechner, nicht über dieses Programm.

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

**Festgelegt: genau eine Datei, `/etc/urbackup-gated.conf`.** Die zeitweise offene Alternative eines Ordners `/etc/urbackup-gated` mit mehreren Dateien ist damit entschieden und entfällt — der Umfang der Einstellungen rechtfertigt sie nicht. Die Datei muss mindestens enthalten: die Liste erlaubter SSIDs sowie die Zeiten und Intervalle, soweit sie einstellbar sein sollen statt fest im Code.

**Änderungen wirken erst nach einem Neustart des Dienstes.** Die Konfiguration wird ein einziges Mal beim Start gelesen, nicht bei jeder Bewertung; es gibt bewusst keine Überwachung der Datei. Wer die Erlaubnisliste oder ein Intervall ändert, muss anschließend `systemctl --user restart urbackup-gated` aufrufen. Das gilt in beide Richtungen: Auch eine im laufenden Betrieb beschädigte Datei löst den Fail-safe (s. u.) **nicht** sofort aus, sondern erst beim nächsten Start.

**Die ausgelieferte Konfiguration enthält Platzhalter, keine echten SSIDs.** Das Repository ist öffentlich und das README lädt zum Klonen ein; wer ohne einen Blick in die Datei installiert, erlaubte sonst Sicherungen über vier Netze, deren Namen ihm nichts sagen. Ausgeliefert werden deshalb zwei Platzhalter — zwei, damit die Liste als Liste erkennbar bleibt. Eine **leere** Liste ist ebenfalls gültig und bedeutet: Ethernet ja, jedes WLAN nein.

**Der Vergleich bleibt case-sensitiv.** Das ist keine Nachlässigkeit: Auf dem Rechner, für den dieses Werkzeug entstand, sind `lieluX` und `lielux` zwei tatsächlich unterschiedliche, echte Netze. Ein Vergleich ohne Rücksicht auf Groß- und Kleinschreibung würde hier zwei Netze zu einem verschmelzen — und eines davon könnte das falsche sein.

### Format: TOML

**Festgelegt:** Die Datei heißt weiterhin `/etc/urbackup-gated.conf`, ihr Inhalt ist **TOML**. Gelesen wird sie mit `tomllib` aus der Standardbibliothek — vorhanden seit Python 3.11, auf diesem Rechner geprüft (3.12.3). Nur lesend; geschrieben wird die Konfiguration nie.

**Ausschlaggebend war die SSID-Liste.** JSON kennt keine Kommentare, und die Datei wird von Hand gepflegt. YAML wäre eine zusätzliche Abhängigkeit. INI mit `configparser` kennt keine Listen — man müsste an Kommas trennen, und SSIDs dürfen Kommas, Leerzeichen und Anführungszeichen enthalten, wodurch es irgendwann still falsch würde. TOML hat echte Zeichenketten-Arrays mit sauberer Quotierung, dazu Kommentare und getypte Zahlen für die Intervalle.

**Schlüssel englisch wie aller Code:** `allowed_ssids` als Array, dazu eine Gruppe für die Intervalle (Prüftakt regulär und bei offenem Statusfenster, Abstand der Ruhemeldung, Abstand der Fortschrittsmeldung) und eine für die Anzeigedauer der Notifications. Alles außer `allowed_ssids` ist optional und fällt auf Vorgabewerte zurück; fehlerhafte Werte sind dagegen ein Fehler und lösen den Fail-safe aus (s. u.).

### Fail-safe bei fehlender/kaputter Konfiguration

Fehlt `/etc/urbackup-gated.conf`, ist sie nicht lesbar oder inhaltlich fehlerhaft
(z. B. keine gültige SSID-Liste), bleibt `urbackupclientbackend` **gestoppt**
bzw. wird gestoppt — unabhängig davon, welches Netz gerade aktiv ist. Sicherer
Default: eine verpasste Sicherungsgelegenheit ist unkritisch, eine ungeprüft
laufende Sicherung über ein möglicherweise nicht erlaubtes Netz wäre genau
das Risiko, das der Dienst verhindern soll.

**Geprüft wird beim Dienststart**, nicht laufend (s. o., „Änderungen wirken erst nach einem Neustart des Dienstes"). Der Dienst stoppt den Client, zeigt das Fehlerfenster und **beendet sich**; er bleibt nicht in einem halb arbeitsfähigen Zustand. Damit daraus keine Endlosschleife aus Neustart und Fehlerfenster wird, unterscheidet er diesen Abbruch für systemd erkennbar von einem gewöhnlichen Fehlschlag: Auf diesen einen Abbruchgrund wird nicht neu gestartet, auf andere schon.

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

**Auch die Dialogprogramme melden sich dort.** Schlägt `notify-send` oder `yad` fehl — kein Display, kein Session-Bus, ein `notify-send` ohne `--action` —, sieht das ohne Prüfung des Rückgabewerts genauso aus wie „der Nutzer hat nichts angeklickt": keine Ausgabe, kein Fehler, nichts. Der Rückgabewert wird deshalb angesehen und ein Fehlschlag mit der Ausgabe des Programms ins Journal geschrieben. Beim Fehlerfenster wiegt das am schwersten: Es existiert, um einen kaputten Zustand zu erklären; bliebe sein Scheitern stumm, erführe der Nutzer gar nichts.

**Ungepuffert, und das ist Bedingung, nicht Feinheit:** Python puffert die Standardausgabe blockweise, sobald sie kein Terminal ist — unter systemd ist sie immer eine Pipe. Ohne Gegenmaßnahme bliebe das Journal leer, bis der Puffer voll ist oder der Dienst endet. Bei einem Dienst, der tagelang läuft und dessen einziger Diagnosekanal das Journal ist, wäre die Festlegung „landet automatisch im Journal" damit schlicht unwahr. Das Startskript, das `install.sh` erzeugt, schaltet die Pufferung deshalb ab. Der Ort ist bewusst das Startskript und nicht die Unit: So gilt es auch für den Aufruf von Hand bei der Fehlersuche, und nicht nur unter systemd. Eine Prüfung in Stufe 2 sichert das ab — gefunden wurde es genau dort, nachdem eine erwartete Zeile im Protokoll fehlte, obwohl die zugehörige Handlung nachweislich stattgefunden hatte.

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

**Auf welche Aktionen der Hook reagiert, ist Festlegung und nicht Geschmack:** `up`, `down`, `dhcp4-change`, `dhcp6-change` und `connectivity-change`. Alles andere lässt er unbeachtet, insbesondere `vpn-up` und `vpn-down` — der Dienst bewertet physische Verbindungen, ein kommender oder gehender Tunnel geht ihn nichts an (siehe „Ausdrücklich nicht betrachtete Sonderfälle"). Die Liste steht hier und nicht nur im Hook, weil sie bestimmt, **wann** überhaupt neu bewertet wird: Eine Aktion, die hier fehlt, kostet keine Fehlermeldung, sondern bis zu 30 Sekunden Verzögerung — der Zeittakt fängt sie auf, und niemand bemerkt den Unterschied.

**Die Datei heißt `/run/urbackup-gated/network-event`.** Der Name steht hier, weil er die einzige Verabredung zwischen zwei getrennt entwickelten Teilen ist: Der Dispatcher schreibt ihn als root, der Dienst filtert seine Verzeichnisüberwachung darauf. Wer eine der beiden Seiten ändert, ohne die andere zu kennen, bekommt keinen Fehler, sondern ein stilles Ausbleiben der Ereignisse — gedeckt nur noch vom Zeittakt, also mit bis zu 30 Sekunden Verzögerung statt sofort. **Ihr Inhalt spielt keine Rolle**; sie wird nur berührt, nicht beschrieben. Das unterscheidet sie von der Kommandodatei, die einen Zustand trägt (siehe „Manuelles Aktivieren und Deaktivieren").

**Drei Eigenschaften der Überwachung, die nicht Feinheit, sondern Voraussetzung sind:**

- Überwacht wird **das Verzeichnis, nicht die einzelne Datei.** Maßgeblich dafür ist die Kommandodatei: Sie wird atomar per `rename` ersetzt (s. „Manuelles Aktivieren und Deaktivieren"), und eine Überwachung, die an der Datei selbst hängt, verliert dabei stillschweigend ihr Ziel — sie beobachtet danach ein Objekt, das niemand mehr beschreibt, ohne dass ein Fehler auffällt. Für die Netzwerkdatei gilt das nicht: Der Dispatcher berührt sie nur, ihr Inode bleibt erhalten, und eine Dateiüberwachung täte es für sie allein. Die Verzeichnisüberwachung ist trotzdem der richtige Weg — für die Kommandodatei ist sie ohnehin zwingend, und sie deckt beide Dateien mit einem einzigen Beobachter ab.
- Der Beobachter reagiert **ausschließlich auf die beiden bekannten Dateinamen** und ignoriert alles andere im Verzeichnis. Das ist zwingend, weil der Dienst seine `state.json` in dasselbe Verzeichnis schreibt: Ohne diesen Filter würde sein eigener Schreibvorgang die eigene Überwachung auslösen, diese eine neue Bewertung anstoßen und die wieder schreiben — eine Endlosschleife im Sekundentakt.
- Der Beobachter reagiert **ausschließlich auf Ereignisse, die eine Datei verändern**: Anlegen, Ändern, Umbenennen, Löschen und das Schließen nach einem Schreibvorgang. Das bloße **Öffnen** gehört nicht dazu. Der Namensfilter allein genügt nämlich nicht — er trifft nur den einen der zwei Rückkopplungswege. Den anderen öffnet der Dienst selbst: inotify meldet auch das reine Lesen einer Datei, und der Dienst liest die Kommandodatei bei **jedem** Durchlauf. Damit weckt er sich selbst, sobald diese Datei existiert, also ab dem ersten manuellen Schalten — der Dienststart löscht sie, ein frisch gestarteter Dienst zeigt das Verhalten deshalb nicht. Am Zielrechner gemessen, bevor dieser Filter da war: 49 Statusschreibvorgänge in zwei Sekunden statt einem alle 30 Sekunden und dauerhaft ein halber Prozessorkern. **Aufgezählt werden die erlaubten Ereignisarten, nicht die verbotenen** — auch das ist Festlegung: Eine Sperrliste müsste jede Art von Lesezugriff kennen, die `watchdog` meldet, und diese Menge wächst (`IN_OPEN` steht in den Versionen 3, 4 und 6 in der überwachten Maske, `IN_CLOSE_NOWRITE` kommt in Version 6 hinzu). Übersieht sie eine davon, ist die Rückkopplung wieder geschlossen. Der Positivliste fehlt im schlimmsten Fall ein Weck-Ereignis, und dafür gibt es den Zeittakt — dieselbe Abwägung wie beim Aktionsfilter des Dispatchers weiter oben: bis zu 30 Sekunden Verzögerung statt eines Fehlers.

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

Abgefragt wird nicht die primäre Verbindung, sondern **die vollständige Liste aller aktiven Verbindungen**, je Eintrag mit Typ und, bei WLAN, der SSID. Aus dieser Liste geht dann **nur weiter, was Ethernet oder WLAN ist**; Loopback und alles Übrige — Brücken, Tunnel, virtuelle Geräte — fällt heraus und erscheint auch im Status nicht. Das ist die Umsetzung von „alle gleichzeitig aktiven **physischen** Verbindungen" aus den Entscheidungsregeln: Abgefragt wird vollständig, bewertet wird die physische Teilmenge. Das folgt zwingend aus den Entscheidungsregeln: Eine einzige aktive, nicht erlaubte WLAN-Verbindung verbietet den Betrieb, auch wenn sie nicht die primäre Verbindung ist. Eine Abfrage, die nur die primäre Verbindung liefert, wäre für diese Regel unbrauchbar.

**Verbunden ist, was mit „connected" beginnt.** `nmcli` meldet nicht nur `connected`, sondern auch `connected (externally)` für Geräte, deren Verbindung außerhalb von NetworkManager entstand, und `(site only)` bzw. `(local only)` bei eingeschränkter Erreichbarkeit. Alle bezeichnen ein verbundenes Gerät und werden bewertet. Ein Vergleich auf Gleichheit ließe ein etwa per `wpa_supplicant` verbundenes WLAN unbeurteilt — und neben einer Ethernet-Verbindung läse sich das als „erlaubt", also genau als der Ausgang, den die Entscheidungsregeln ausschließen sollen. `disconnected` und `connecting` beginnen nicht mit dem Wort und fallen weiterhin heraus.

**Die SSID gehört zum Gerät, nicht zur Anzahl.** Die WLAN-Abfrage liefert das Feld `DEVICE` mit; damit ist unmittelbar bekannt, zu welchem Funkgerät ein Eintrag gehört. Aus der Anzahl aktiver Einträge auf die Zugehörigkeit zu schließen und ersatzweise den Profilnamen heranzuziehen, war Raterei: Ein Profil lässt sich auf jeden Namen umbenennen, auch auf den eines erlaubten Netzes. Findet sich für ein verbundenes Funkgerät **kein eigener Eintrag** — der Fall „eigener Access Point" —, bleibt die SSID unbestimmt und damit verboten.

**Die SSID wird als Bytefolge gelesen, nicht als Text.** Abgefragt wird `SSID-HEX`; die Dekodierung nach UTF-8 geschieht im eigenen Code, nicht dekodierbare Stellen werden ersetzt und die Ersetzung ins Journal geschrieben. Grund: Eine SSID ist nach 802.11 eine **Bytefolge ohne vorgeschriebene Kodierung**, und `LC_ALL=C` legt den Zeichensatz auf ASCII fest. Wie `nmcli` einen Umlaut unter dieser Locale darstellen würde — ersetzen, maskieren, roh durchreichen —, ist damit gleichgültig; die Frage stellt sich nicht mehr. Ein Dekodierfehler in der Abfrage hätte den Dienst beendet.

*Der Preis, ausdrücklich benannt:* Eine SSID, die nicht UTF-8 ist, passt nach der Ersetzung auf keinen Eintrag der Erlaubnisliste und ist damit verboten. In TOML wäre sie ohnehin nicht abbildbar. Ohne die Journalzeile wäre aber nicht erkennbar, warum in diesem Netz nie gesichert wird.

Sprachabhängigkeit der Ausgabe ist damit vollständig beseitigt, nicht nur
verringert: Laut `nmcli`-Handbuch, Abschnitt „INTERNATIONALIZATION NOTES",
hängt die Ausgabe grundsätzlich von der Locale-Umgebung ab; die dort selbst
empfohlene, verlässliche Lösung ist der Aufruf als `LC_ALL=C nmcli …`. `-t`
regelt nur das Format (maschinenlesbare Feldtrennung), nicht die Sprache der
Werte — beides zusammen (`LC_ALL=C nmcli -t -f …`) ist notwendig und
laut Handbuch ausreichend.

## Prüfung und Abnahme

Die Prüfung ist in drei Stufen geteilt, weil sich die drei nach ihren Voraussetzungen unterscheiden, nicht nach ihrem Gegenstand: Stufe 1 braucht nichts, Stufe 2 braucht root und ein eigenes System, Stufe 3 braucht einen echten Menschen an einem echten Desktop. Ungefähr neun Zehntel sind damit automatisiert.

### Stufe 1: Unit-Tests

`tests/run-unit.sh`, ohne root, ohne Container, ohne zusätzliche Pakete (`unittest` aus der Standardbibliothek). Statt `subprocess` wegzumocken liegen in `tests/unit/stubs/` Ersatzprogramme für `nmcli`, `urbackupclientctl`, `systemctl` und `sudo`, die über `PATH` bzw. über die Modulkonstanten vorgeschaltet werden und jeden Aufruf mitschreiben — geprüft wird damit die **tatsächlich gebaute Kommandozeile**, nicht eine Attrappe davon. Die nmcli-Ausgaben liegen als echte Beispieldateien unter `tests/unit/scenarios/`, je Szenario ein Ordner.

Abgedeckt: die vollständige Entscheidungsmatrix, das Zerlegen der nmcli-Ausgabe samt Escaping, die Konfigurationsprüfung mit ihren Ablehnungen, die Flag-Semantik samt atomarem Schreiben, das Parsen des Client-Status in beiden Ausgabeformen, die Textaufbereitung und die Meldelogik des Dienstes — welcher Zustandswechsel eine Meldung auslöst und welcher nicht (s. „Ein dritter Zustand, der keinen Wechsel auslöst").

Dazu vier Festlegungen, die lange nur im Code standen und von nichts geprüft wurden: die `yad`-Prüfung beim Dienststart samt ihrer Meldung; das Löschen des Nutzer-Flags beim Start, aus dem sich „bei jedem Dienststart aktiviert" ergibt; die Anzeige des Alters der Statusangabe und die Ablehnung einer unverstandenen `schema_version` durch das Kommandozeilenwerkzeug; und dass ein blockierender Notify-Aufruf die Prüfschleife nicht anhält — geprüft mit einer Attrappe, die **wirklich** blockiert, bis der Test sie freigibt, statt über eine Zeitmessung.

Die Meldelogik liegt im Dienstmodul, das für die Verzeichnisüberwachung `watchdog` braucht. Damit Stufe 1 ihre Zusage „ohne zusätzliche Pakete" hält, setzt die Testunterstützung dafür Platzhalter ein, solange das Paket fehlt, und benutzt das echte, sobald es installiert ist — geprüft wird so oder so der unveränderte Dienstcode, denn die Meldelogik rührt `watchdog` nicht an.

Dass die Tests wirklich greifen, ist selbst geprüft: Sieben absichtlich eingebaute Fehler — Ethernet hebelt verbotenes WLAN aus, Nutzer-Einspruch wird ignoriert, Profilname statt SSID, WLAN-Scan nicht mehr unterdrückt, `running_processes` nicht mehr gelesen, Loopback zählt als Verbindung, Zeitstempel ohne Zeitzone — wurden alle sieben erkannt.

### Stufe 2: Integrationstests im Container

`tests/container/run.sh` baut das Abbild aus `tests/container/Dockerfile`, startet den Container und führt darin `tests/container/inside/run.sh` aus. Voraussetzung ist ein erreichbarer Docker-Daemon und privilegierter Modus, weil systemd als PID 1 im Container laufen muss; das Repository wird nur lesend eingehängt, am Wirtssystem wird nichts verändert.

Gefälscht wird darin ausschließlich, was ein Container prinzipiell nicht kann oder was nur Ballast wäre: der UrBackup-Client (eine Unit **gleichen Namens**, die `sleep` ausführt, sodass Starten, Stoppen, Aktivieren und Abfragen von unserer Seite aus identisch aussehen), `nmcli` (kein Container erzeugt eine echte WLAN-Assoziation), `notify-send` (kein Notification-Server vorhanden; die Aufrufe werden mitgeschrieben, damit die angebotenen Schaltflächen prüfbar bleiben) und der Paketmanager (s. u.).

Weil NetworkManager nur durch den `nmcli`-Stub vertreten ist, fehlt auch das Verzeichnis, das er sonst mitbrächte — `/etc/NetworkManager/dispatcher.d`. Der Testaufbau legt es deshalb selbst an. Das ist keine Feinheit: `install.sh` legt seinen Dispatcher-Hook dort ab und erzeugt keine übergeordneten Verzeichnisse, bricht also ohne dieses eine `mkdir` mitten im Lauf ab und reißt jeden folgenden Prüfpunkt mit.

Was im Einzelnen geprüft wird, steht in `tests/container/inside/run.sh` — jeder Prüfpunkt trägt dort seinen Klartext. Hier wird es absichtlich **nicht** aufgezählt: Eine zweite Fassung derselben Liste in Prosa veraltet still, sobald sich ein Prüfpunkt ändert, und niemand merkt es. Der Gegenstand der Stufe lässt sich in einem Satz sagen — alles, was root und ein Wegwerf-System braucht: Installation und Deinstallation, die Enge der sudoers-Freigabe, der Aktionsfilter des Dispatchers, das Gating von Ende zu Ende über die Trigger-Dateien, die Selbstheilung nach einer Neuinstallation des UrBackup-Clients, und der Fail-safe bis auf sein Fehlerfenster.

Das Image bringt `yad` bewusst **nicht** mit; geprüft wird gerade, dass der Installer dessen Fehlen erkennt und die Nachinstallation anbietet (s. „Zweite Folge, den Installer betreffend"). Der Paketmanager ist dafür wie `nmcli` und `notify-send` durch einen mitschreibenden Stub ersetzt — echtes `yad` zöge GTK ins Image, ohne dass darin je etwas angezeigt würde.

Ein bewusster Verzicht: Der Dienst wird im Container **direkt** gestartet, nicht über `systemd --user`. Eine Nutzersitzung mit eigenem Session-Bus im Container aufzubauen kostet viel Aufwand, der in Container-Klempnerei fließt statt in Erkenntnis über unseren Code. Die Unit-Datei wird stattdessen statisch auf Syntaxfehler geprüft; ihr Zusammenspiel mit der echten Sitzung fällt in Stufe 3.

### Stufe 3: Abnahme von Hand

Was hier steht, ist der Rest, der sich nicht sinnvoll automatisieren lässt: die Erscheinung auf **diesem** Desktop (ein Container würde dunst unter Xvfb benutzen, also einen anderen Notification-Server — ein grüner Test dort sagt über Plasma nichts) und ein echter WLAN-Wechsel (sauber fälschen ließe er sich nur mit `mac80211_hwsim` und `hostapd`, also mit einem Kernel-Modul auf dem Wirt — unverhältnismäßig gegenüber einer Handprüfung von dreißig Sekunden).

1. **Meldung und Schaltflächen.** Eine Meldung abwarten. Erwartet: `Details` ist vorhanden, dazu genau eine der beiden Schaltflächen `Deactivate` bzw. `Activate` passend zum aktuellen Nutzer-Zustand; Anzeigedauer wie konfiguriert; die Dauer pausiert, solange der Mauszeiger über der Meldung steht.
2. **Live-Fenster.** `Details` klicken. Erwartet: Das Fenster öffnet sich, der Inhalt wird im Takt von etwa 5 Sekunden **überschrieben** und wächst nicht an; solange es offen ist, kommen keine Meldungen; nach dem Schließen kommen sie wieder.
3. **Echter Netzwechsel.** Vom erlaubten Netz auf den Handy-Hotspot wechseln. Erwartet: Der Client stoppt binnen 30 Sekunden, und die Meldung nennt die SSID als Grund. Zurück ins erlaubte Netz: Der Client startet wieder.
4. **Dockingstation-Strenge.** Ethernet und ein fremdes WLAN gleichzeitig aktiv. Erwartet: Es wird **nicht** gesichert — das ist der bewusst gewählte Preis. WLAN abschalten: Es läuft wieder.
5. **Handschalter.** Deaktivieren über die Schaltfläche und über `urbackup-gated-ctl deactivate`, beides wirkt. Dann im verbotenen Netz aktivieren: Der Client darf **nicht** starten.
6. **Fail-safe, nur die Anzeige.** Die Konfiguration absichtlich beschädigen und den Dienst neu starten. Erwartet: ein **Fehlerfenster** mit der konkreten Ursache. Dass der Client dabei gestoppt wird, dass der Dienst mit dem vereinbarten Rückgabewert endet und dass er sich nicht in einer Schleife neu startet, prüft Stufe 2 — hier bleibt nur, was ein Auge braucht.
7. **Abmelden.** Erwartet: Der Client wird beim Beenden der Sitzung gestoppt.
8. **Erstes echtes Backup.** Die Fortschrittsanzeige gegen die Wirklichkeit prüfen. Beim Programmieren war die genaue JSON-Struktur von `urbackupclientctl status` nicht verifizierbar, weil das Client-Backend nicht lief; der Parser deckt deshalb beide plausiblen Formen ab (`running_processes`-Liste oder Felder direkt auf oberster Ebene) und fällt sonst geordnet auf „nicht erreichbar" zurück. Erwartet: Die angezeigten Werte für Menge, Anteil und Geschwindigkeit entsprechen dem, was tatsächlich läuft.

**Ergebnis der Abnahme:** alle acht Punkte bestanden, geprüft am 12. September 2026 auf dem Zielrechner. Damit ist auch die letzte inhaltlich offene Annahme des Vorhabens erledigt — die Zahlen aus `urbackupclientctl status` sind gemessen und stimmen.

# Anhang

## Code-Review vom 12. September 2026

Geprüft wurde der Stand `5d813c6` auf `claude-workbench` durch eine zweite, unbeteiligte Instanz.

**Umfang:** alles Versionierte — die acht Python-Module unter `src/urbackup_gated/`, `install.sh`, `uninstall.sh`, die fünf Dateien unter `packaging/`, die Unit-Suite samt Attrappen und Szenarien, die Container-Stufe samt Dockerfile und Attrappen, README, diese Doku, Fahrplan und Status. Am Rechner wurde nur lesend gearbeitet; ausgeführt wurden beide Teststufen (Stufe 1: 101 Tests, Stufe 2: 71 Prüfpunkte, jeweils vollständig bestanden) sowie einige lesende Abfragen.

**Was hier steht und was nicht:** Die aufgeworfenen echten Mängel sind abgestellt; sie werden nicht historisch mitgeführt, das blähte die Doku nur auf. Festgehalten ist ausschließlich, was ein **künftiges Review** sonst erneut als Befund anzeigen würde, obwohl es eine bewusste Entscheidung ist oder bereits geprüft wurde.

### Geprüft, kein Mangel

**`self._wake.clear()` steht nach `wait()`, nicht davor.** Der Einwand lautet, ein Ereignis zwischen beiden Aufrufen gehe verloren. Es geht nicht verloren: `clear()` ist die letzte Anweisung des Schleifendurchlaufs, unmittelbar danach folgt der nächste mit einer vollständigen Neubewertung. Beide Trigger tragen **Zustand** und kein flüchtiges Signal — die Kommandodatei ihren Inhalt, die Netzwerkdatei ihre Existenz —, und beides wird bei jeder Bewertung neu gelesen. Verloren geht höchstens ein überflüssiger Durchlauf.

**Der Rechner als eigener Access Point.** Betreibt das WLAN-Gerät selbst einen Hotspot, steht es auf `connected`, führt aber in `nmcli device wifi list` keinen Eintrag mit `ACTIVE=yes`. Die SSID bleibt damit unbestimmt, und unbestimmt heißt verboten. Das ist die gewollte konservative Richtung, kein Versehen.

**Die Container-Stufe startet den Dienst unmittelbar, nicht über `systemd --user`.** Begründet unter „Stufe 2: Integrationstests im Container". Das Zusammenspiel mit der echten Sitzung ist Gegenstand der Handabnahme.

### Bewusst so und nicht anders

**Diese Doku besteht aus den Zusammenhängen und diesem Anhang, sonst nichts.** Nach der allgemeinen Methodik käme eine dreiteilige Segmentstruktur, und Segment 3 entstünde vor der Implementierung. Für ein Vorhaben dieser Größe wurde am 9. September ausdrücklich entschieden, die Doku nach Segment 1 einzufrieren und daraus heraus zu implementieren; die beiden leeren Segmentüberschriften sind mit der Freigabe von 1.0.0 entfernt worden, weil sie nichts als eine unerfüllte Erwartung trugen. Das ist eine Abweichung mit Ansage, keine Lücke.

**Die Dockingstation-Strenge** — Ethernet und ein fremdes WLAN gleichzeitig, und es wird nicht gesichert — ist der ausdrücklich benannte Preis der Entscheidungsregeln, nicht deren Fehler. Siehe „Preis dieser Entscheidung, ausdrücklich benannt".

**Unbekannte Schlüssel in der Konfiguration werden übergangen, nicht bemängelt.** Ein Tippfehler in einem Intervallnamen fällt damit nicht auf; der Vorgabewert gilt weiter. Das ist entschieden und gewollt: Für alles außer der Erlaubnisliste soll der Dienst aus der Lage das Beste machen, statt die Arbeit zu verweigern. Die Erlaubnisliste selbst ist dagegen Pflicht, und ein **fehlerhafter Wert** — eine Zeichenkette statt einer Zahl, eine Null, ein negatives Intervall — löst weiterhin den Fail-safe aus. Die Grenze verläuft zwischen „nicht genannt" und „falsch genannt", nicht zwischen wichtig und unwichtig.
