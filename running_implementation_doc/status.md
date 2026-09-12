# Status

Abgearbeitete Fahrplaneinträge, chronologisch. Begründungen stehen nicht hier, sondern im zuständigen Kapitel der Implementierungsdoku.

## Findung und Fixierung

- GitHub-Repo angelegt und nach `~/git/urbackup-gated` geklont.
- Branches `dev` (Hauptpfad) und `claude-workbench` (Werkbank) angelegt.
- Dienstname festgelegt: `urbackup-gated`.
- Roadmap und Status aus dem Konzept in eigene Dateien ausgelagert.
- Konzept in Segment 1 der `implementation.md` eingearbeitet, `concept.md` dabei gelöscht.
- Fixierung abgeschlossen: Systemintegration und Rechteaufteilung, Fail-safe bei kaputter Konfiguration, Protokollierung, Testbarkeit über `state.json`, Netzwerk-Ereigniserkennung, SSID-Abfrage, Live-Statusfenster mit `yad`, Entscheidungsregeln, manueller Nutzer-Zustand, Auslösepunkte, Ablageort und Kommandodatei-Protokoll.

## Implementierung

- Dienst, Kommandozeilenwerkzeug, Installations- und Deinstallationsroutinen, Packaging und README.
- Unit-Suite (Stufe 1) und Container-Integrationstests (Stufe 2), Abnahme von Hand (Stufe 3) in der Doku beschrieben.

## Nacharbeit nach der ersten Prüfung des Gesamtstands

- Meldelogik korrigiert: Ein nicht erreichbares Backend gilt nicht mehr als Zustandswechsel, wodurch nach jedem netzbedingten Stopp eine falsche Meldung über einen Serververlust entfiel. Erste Unit-Tests der Meldelogik.
- Installer bietet fehlende Laufzeitpakete (`yad`, `libnotify-bin`) zur Nachinstallation an, statt abzubrechen; Schalter `--yes` für unbeaufsichtigte Läufe.
- Container-Stufe erstmals lauffähig gemacht — sie war seit ihrer Entstehung nie ausgeführt worden.
- Drei falsch-grüne Prüfpunkte der Container-Stufe gehärtet.
- TOML-Festlegung und Schema von `state.json` aus der Roadmap in die Implementierungsdoku überführt; Roadmap auf die offenen Punkte zurückgeschnitten.

## Phase 1 und 2 der Nacharbeit

- Installation selbsttragend gemacht: Deinstaller und Anwenderdokumentation landen im System, ein Manifest steuert die Deinstallation, die User-Unit liegt unter `/usr/local/lib/systemd/user`, die Konfigurationsdatei trägt eine Kurzanleitung.
- Kapitel „Installation und Deinstallation" mit der Definition der Ordnerstruktur aufgenommen.
- Die vier vorgeschriebenen, bis dahin ungeprüften Verhaltensweisen mit Unit-Tests abgedeckt; Selbstheilung und der nicht-optische Teil des Fail-safe aus der Handabnahme in den Container gezogen.
- Pufferung der Dienstausgabe abgeschaltet: Ohne das erreichte keine Meldung das Journal, solange der Dienst lief.

## Nacharbeit aus dem Code-Review

- Schritt 1 — Fehler dürfen nicht verschwinden: hängendes `systemctl`, stumme Dialogaufrufe, endgültig verworfene Meldungen, schiefe Zeitmarken.
- Schritt 2 — Netzbewertung: extern konfigurierte Geräte werden bewertet, SSID-Zuordnung über das Gerät, SSID als Bytefolge statt als Text.
- Schritt 3 — Installation, Unit und Werkzeuge: Unit an der grafischen Sitzung, ehrliche Abbruchmeldung bei abgelehnter sudoers-Datei, Neustart bei Aktualisierung, `python3-watchdog` wird angeboten, Kommandowerkzeug verweigert den Schreibweg als root, doppelte Verzeichnisprüfung entfernt.
- Schritt 4 — Dateirechte und Doku-Nachführung: Status- und Kommandodatei wieder lesbar, Aktionsliste des Dispatchers dokumentiert, Selbstwiderspruch zu `install.sh` aufgelöst, ausgelieferte Konfiguration mit Platzhaltern, Anhang abgeschlossen.
- Schritt 5 — Statusfenster: `\f`-Protokoll, Erkennen der geschlossenen Pipe und die Fensterlogik im Dienst geprüft. Damit ist kein Modul mehr ungeprüft.

## Befunde der ersten Installation auf dem Zielrechner

- Schritt 1 — Die Hauptschleife weckt sich nicht mehr selbst: Der Verzeichnisbeobachter unterscheidet jetzt zusätzlich zum Dateinamen die Art des Ereignisses, weil inotify auch das bloße Lesen meldet und der Dienst die Kommandodatei in jedem Durchlauf liest.
- Schritt 2 — Die Ruhemessung der Container-Stufe wird nach dem Anlegen der Kommandodatei wiederholt. Die bestehende Messung lief, bevor die Datei existierte, und konnte den Fehler deshalb nicht sehen.
- Schritt 3 — Über einen Client, den der Dienst selbst gestoppt hat, zeigt die Statusanzeige keine Erreichbarkeitsdiagnose mehr, sondern ein `-`. Bei laufender oder unbekannter Unit bleibt die Diagnose stehen.
