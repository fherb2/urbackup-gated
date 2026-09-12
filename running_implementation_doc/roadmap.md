# Roadmap

## Arbeitsweise für die Nacharbeit

Ein **Schritt** ist die Einheit der Freigabe: ein Plan, eine Zustimmung. Ein **Commit** ist die Einheit der Lösung: genau ein behobenes Problem je Commit. Ein Schritt umfasst deshalb in der Regel mehrere Commits. So bleibt in der Historie nachvollziehbar, was womit gelöst wurde, ohne dass für jede Kleinigkeit ein eigener Plan vorgelegt und einzeln freigegeben werden muss.

## Phase 1 — Nacharbeit aus dem Code-Review

Grundlage ist der Bericht vom 12. September 2026. Die Befunde sind nachgeprüft; einer wurde widerlegt und steht mit Begründung im Anhang der Implementierungsdoku.

### Schritt 4 — Dateirechte und Doku-Nachführung

- **Statusdatei und Kommandodatei sind 0600**, die Doku und der `tmpfiles.d`-Kommentar versprechen Lesbarkeit für alle. Eine der beiden Seiten hat unrecht. Ursache ist, dass `tempfile.NamedTemporaryFile` mit 0600 anlegt und `os.replace` den Modus beibehält.
- **Die Aktionsliste des Dispatcher-Hooks** steht nur im Hook. Sie ist eine Verabredung zwischen zwei Teilen und gehört in die Doku, so wie dort schon der Dateiname steht.
- **„Einzige Instanz, die es je startet oder stoppt, ist `urbackup-gated`"** — `install.sh` stoppt den Client mit `disable --now` ebenfalls, auch eine gerade laufende Sicherung. Selbstwiderspruch der Doku; gehört zusätzlich in den Installationsabschnitt der README.
- **Die ausgelieferte Konfiguration nennt vier private SSIDs.** Ersetzt durch `YourUnlimitedWLANSSID_1` und `YourUnlimitedWLANSSID_2`, damit die Liste als Liste erkennbar bleibt. Zu bedenken: Die echten Namen stehen auch in der Implementierungsdoku; sie aus der Konfiguration zu nehmen, entfernt sie nicht aus dem Repository.
- **Der Anhang wird abgeschlossen:** Dass unbekannte Konfigurationsschlüssel stillschweigend übergangen werden, ist eine bewusste Entscheidung — nicht Funktionsverweigerung, sondern das Beste aus der Lage machen. Ein künftiges Review soll das nicht erneut anzeigen.

### Schritt 5 — Die letzte ungeprüfte Einheit

Von `ui.py` ist der Fehlerpfad inzwischen abgedeckt; offen bleibt das Statusfenster: das `\f`-Protokoll, das Erkennen der geschlossenen Pipe, der Wechsel des Prüftakts bei offenem Fenster und die Unterdrückung der Meldungen. Mit einer `yad`-Attrappe, die ihre Standardeingabe mitschreibt, ist das ohne Anzeige prüfbar. Dazu die Fensterlogik im Dienst — `_drain_requests` und `_open_window` —, die heute nur mittelbar berührt wird.

## Phase 2 — Übernahme in den Hauptpfad

Push der Werkbank, dann echter Merge nach `dev` mit vollständiger Historie, ausdrücklich kein Squash.

## Phase 3 — Abnahme von Hand

Stufe 3 auf dem Zielrechner, beschrieben unter „Stufe 3: Abnahme von Hand". Acht Punkte, alle auf das beschränkt, was ein Auge oder ein echtes Funkgerät braucht.

Punkt 8 ist die **einzige inhaltlich offene Annahme** des ganzen Vorhabens: Die genaue JSON-Struktur von `urbackupclientctl status` konnte nicht verifiziert werden, weil das Client-Backend beim Programmieren nicht lief. Ob die Zahlen stimmen, zeigt erst die erste echte Sicherung. Durch keinen Test ersetzbar, und damit der eigentliche Schlusspunkt.

**Neu zu beachten:** Seit die Unit an `graphical-session.target` hängt, ist bei der Abnahme mitzuprüfen, dass der Dienst mit der grafischen Sitzung tatsächlich startet und mit ihr endet — und dass er sich in einer reinen SSH-Sitzung gar nicht erst meldet.

## Nicht vergessen

Das Container-Abbild `urbackup-gated-tests` liegt nach den Prüfläufen mit `KEEP_IMAGE=1` noch auf dem Rechner — einige hundert Megabyte. Es wird für die restliche Nacharbeit noch gebraucht; nach der Abnahme kann es weg (`docker image rm urbackup-gated-tests`, oder ein Lauf ohne `KEEP_IMAGE`).
