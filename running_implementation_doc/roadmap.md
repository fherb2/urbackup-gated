# Roadmap

## Arbeitsweise für die Nacharbeit

Ein **Schritt** ist die Einheit der Freigabe: ein Plan, eine Zustimmung. Ein **Commit** ist die Einheit der Lösung: genau ein behobenes Problem je Commit. Ein Schritt umfasst deshalb in der Regel mehrere Commits. So bleibt in der Historie nachvollziehbar, was womit gelöst wurde, ohne dass für jede Kleinigkeit ein eigener Plan vorgelegt und einzeln freigegeben werden muss.

## Phase 1 — Nacharbeit aus dem Code-Review

Grundlage ist der Bericht vom 12. September 2026. Die Befunde sind nachgeprüft; einer wurde widerlegt und steht mit Begründung im Anhang der Implementierungsdoku, zwei betreffen bereits getroffene Entscheidungen.

### Schritt 1 — Fehler dürfen nicht verschwinden

Vier Stellen, an denen der Dienst still etwas verliert: eine Ausnahme, eine Meldung, oder beides.

- **Ein hängendes `systemctl` beendet den Dienst mit Traceback.** Die Abfragen in `client.py` fangen keine Zeitüberschreitung; sie läuft bis in die Hauptschleife durch. Für den Nutzer: eine grundlos abgebrochene Sicherung ohne Meldung.
- **Ein fehlschlagendes `notify-send` oder `yad` hinterlässt keine Spur.** Der Rückgabewert wird nicht angesehen; kein Display, kein Session-Bus, ein zu altes `notify-send` — alles sieht aus wie „keine Aktion gewählt". Die Doku verspricht, dass Fehler im Journal landen.
- **Meldungen werden verworfen, solange eine andere auf dem Bildschirm hängt** — und zwar endgültig, weil der Vorzustand unabhängig davon fortgeschrieben wird. Ein Zustandswechsel geht damit nicht verspätet, sondern gar nicht ein.
- **Die Zeitmarken der periodischen Meldungen** werden nur für den gerade aktiven Zweig fortgeschrieben, wodurch nach einer langen Sicherung die Ruhemeldung sofort hinterherkommt.

### Schritt 2 — Netzbewertung schärfen

- **Extern konfigurierte Geräte fallen durch.** `nmcli` meldet für sie `connected (externally)`; der Vergleich auf Gleichheit übersieht das. Ein außerhalb von NetworkManager verbundenes WLAN würde damit nicht bewertet — genau die Richtung, die die Entscheidungsregeln ausschließen sollen. Am System bestätigt, heute folgenlos, weil es nur Loopback und Brücke betrifft.
- **Nicht-ASCII-SSIDs.** Ungeprüfte Vermutung: Unter `LC_ALL=C` könnte `nmcli` Umlaute ersetzen oder roh ausgeben. Ein Dekodierfehler beendete den Dienst. Abzusichern ist zunächst nur der Absturz; die eigentliche Lösung braucht einen Beleg, also einen Hotspot mit Umlaut im Namen.
- **Zuordnung der SSID bei mehreren WLAN-Geräten** über das Feld `DEVICE` statt über den Profilnamen. Ersetzt eine fragile Sonderbehandlung durch eine eindeutige Zuordnung.

### Schritt 3 — Installation, Unit und Werkzeuge

- **Die Unit startet bei jeder Anmeldung, nicht nur in der Desktop-Sitzung.** `WantedBy=default.target` wird auch bei einer SSH-Anmeldung erreicht, `After=` wartet auf nichts, was nicht ohnehin startet. Folge: Der Dienst gatet auch ohne Desktop, und `yad` kann für die ganze Sitzung ohne Anzeige laufen. **Entscheidung nötig**, bevor gebaut wird: Soll der Dienst an die grafische Sitzung gebunden werden und in einer reinen SSH-Sitzung gar nicht laufen?
- **„nothing installed" ist unwahr**, wenn die sudoers-Prüfung fehlschlägt — zu dem Zeitpunkt liegen Paket, Wrapper, Deinstaller und Doku bereits. Die sudoers-Datei gehört vor die erste abgelegte Datei.
- **Eine Neuinstallation startet den laufenden Dienst nicht neu**, der alte Code läuft bis zur Abmeldung weiter.
- **`python3-watchdog` wird verlangt, `yad` angeboten** — ohne Grund für den Unterschied.
- **Das Kommandowerkzeug als root** hinterlässt eine root-eigene Kommandodatei, die der Dienst nicht lesen kann und die er bei jedem Takt bemängelt.
- **`check_directory` wird doppelt aufgerufen**, einmal mit sauberer Meldung, einmal als Traceback.

### Schritt 4 — Dateirechte und Doku-Nachführung

- **Statusdatei und Kommandodatei sind 0600**, die Doku und der `tmpfiles.d`-Kommentar versprechen Lesbarkeit für alle. Eine der beiden Seiten hat unrecht.
- **Die Aktionsliste des Dispatcher-Hooks** steht nur im Hook. Sie ist eine Verabredung und gehört in die Doku, so wie dort schon der Dateiname steht.
- **„Einzige Instanz, die es je startet oder stoppt, ist `urbackup-gated`"** — `install.sh` stoppt den Client mit `disable --now` ebenfalls, auch eine gerade laufende Sicherung. Selbstwiderspruch der Doku; gehört zusätzlich in den Installationsabschnitt der README.
- **Der Anhang wird abgeschlossen**, sobald feststeht, welche Befunde als bewusste Entscheidung stehen bleiben.

### Schritt 5 — Die letzte ungeprüfte Einheit

`ui.py` ist das einzige Modul ohne jede Prüfung: die gebaute `notify-send`-Kommandozeile, das `\f`-Protokoll des Statusfensters, das Erkennen der geschlossenen Pipe, der Fehlerdialog. Mit einer `yad`-Attrappe, die ihre Standardeingabe mitschreibt, ist das ohne Anzeige prüfbar — das hatte ich zu früh der Handabnahme zugeschlagen. Dazu die Fensterlogik im Dienst, die heute nur mittelbar berührt wird.

### Offene Entscheidungen, bevor der jeweilige Schritt beginnt

- **Schritt 3:** Bindung der Unit an die grafische Sitzung (siehe oben).
- **Unbekannte Konfigurationsschlüssel** werden stillschweigend übergangen; ein Tippfehler im Schlüsselnamen wirkt wie eine bewusst weggelassene Angabe. Am 11. September wurde entschieden, hier nicht die Arbeit zu verweigern. Bleibt es dabei, gehört die Entscheidung in den Anhang.
- **Die ausgelieferte Konfiguration nennt vier private SSIDs.** Das Repository ist öffentlich. Wer installiert, ohne die Datei anzusehen, erlaubt Sicherungen in vier ihm unbekannten Netzen. Die leere Liste wäre zugleich der sicherste Startzustand. Zu bedenken: Die Namen stehen auch in dieser Doku; sie aus der Konfiguration zu nehmen, entfernt sie nicht aus dem Repository.

## Phase 2 — Übernahme in den Hauptpfad

Push der Werkbank, dann echter Merge nach `dev` mit vollständiger Historie, ausdrücklich kein Squash.

## Phase 3 — Abnahme von Hand

Stufe 3 auf dem Zielrechner, beschrieben unter „Stufe 3: Abnahme von Hand". Acht Punkte, alle auf das beschränkt, was ein Auge oder ein echtes Funkgerät braucht.

Punkt 8 ist die **einzige inhaltlich offene Annahme** des ganzen Vorhabens: Die genaue JSON-Struktur von `urbackupclientctl status` konnte nicht verifiziert werden, weil das Client-Backend beim Programmieren nicht lief. Ob die Zahlen stimmen, zeigt erst die erste echte Sicherung. Durch keinen Test ersetzbar, und damit der eigentliche Schlusspunkt.

## Nicht vergessen

Das Container-Abbild `urbackup-gated-tests` liegt nach den Prüfläufen mit `KEEP_IMAGE=1` noch auf dem Rechner — einige hundert Megabyte. Es wird für die restliche Nacharbeit noch gebraucht; nach der Abnahme kann es weg (`docker image rm urbackup-gated-tests`, oder ein Lauf ohne `KEEP_IMAGE`).
