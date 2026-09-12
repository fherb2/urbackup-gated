# Roadmap

Sechs Phasen bis zur Abnahme. Die Reihenfolge ist nicht beliebig: Alles, was den Code noch verändert, liegt vor dem Review; alles, was den Nutzer an den Rechner bindet, dahinter.

## Phase 1 — Installation rund machen

Letzte inhaltliche Änderung am Produkt. Muss vor das Review, sonst begutachtet die zweite Instanz einen Stand, der sich unmittelbar danach ändert.

- **Deinstallation und Doku mitinstallieren.** Heute bleiben `uninstall.sh` und `README.md` ausschließlich im Klon. Wer den Klon nach der Installation wegwirft — nach dem übrigen Entwurf völlig plausibel, es wird ja alles kopiert —, hat keinen sauberen Weg zurück. Künftig landen beide im System, die Deinstallation über ein Kommando neben den beiden vorhandenen.
- **Manifest.** `install.sh` schreibt die Liste dessen, was es abgelegt hat; `uninstall.sh` arbeitet daraus, statt die Pfade ein zweites Mal zu führen. Damit entfällt die Doppelpflege, und die Deinstallation entfernt per Konstruktion genau das, was installiert wurde. Im Manifest steht auch der Dienstnutzer, damit die Deinstallation ihn nicht raten muss.
  Zwei Dinge bleiben außerhalb des Manifests, weil sie keine Dateien sind: Die Konfigurationsdatei bleibt absichtlich stehen, und der UrBackup-Dienst wird wieder in den Systemstart genommen.
- **Kommentarkopf in der Konfigurationsdatei.** Kurz, was der Dienst tut; der Pfad zur vollständigen Anwenderdokumentation; der Befehl zum Deinstallieren samt Hinweis darauf, was dabei mit dem UrBackup-Dienst geschieht.
- **Kapitel „Installation und Deinstallation"** in der Implementierungsdoku, einschließlich der Definition der Ordnerstruktur.
- **Ort der User-Unit:** Umzug von `/etc/systemd/user` nach `/usr/local/lib/systemd/user`. Der Rest der Software liegt unter `/usr/local`; `/etc/systemd/…` ist dem Administrator vorbehalten, nicht dem Mitgelieferten. Beide Pfade sind am System als Suchpfad nachgewiesen.
- **Container-Prüfpunkte** für all das.

## Phase 2 — Testlücken schließen

Vier Festlegungen der Implementierungsdoku, die im Code umgesetzt, aber von keiner Prüfstufe abgedeckt sind. Jeder Eintrag nennt die Stelle, die ihn vorschreibt — daran ist später erkennbar, dass es um die Absicherung einer Vorgabe geht und nicht um einen nachträglichen Einfall.

- **`yad`-Prüfung beim Dienststart.** Der Dienst prüft beim Start, ob `yad` vorhanden ist, und schreibt dessen Fehlen ins Journal. Vorgeschrieben in „Folge daraus, die beim Programmieren nicht untergehen darf" — die Doku markiert diesen Punkt selbst als einen, der nicht untergehen darf.
- **Alter der Statusangabe.** Das Kommandozeilenwerkzeug zeigt an, wie lange das letzte Schreiben her ist. Vorgeschrieben in „Zustand, Merken zwischen Aufrufen und Statusabfrage".
- **Ablehnung einer unverstandenen `schema_version`.** Vorgeschrieben in „Schema von `state.json`". Geprüft wird heute nur, dass die Version geschrieben wird — nie, dass eine falsche zurückgewiesen wird.
- **Blockierender Notify-Aufruf** hält die Prüfschleife nicht an. Vorgeschrieben in „Konsequenz für die Umsetzung: Da dieser Aufruf blockiert…". Der Container-Stub kehrt sofort zurück, blockiert also nie — der Fall wird von keiner Stufe erzeugt.

Dazu zwei Abnahmepunkte, die entgegen der Begründung von Stufe 3 weder Anzeige noch Funkgerät brauchen und deshalb in den Container umziehen:

- **Selbstheilung** (Stufe 3, Punkt 7). Sie ist die Begründung für den dritten `sudoers`-Eintrag und wird bis heute von keinem Test durchlaufen — im Container nicht einmal nebenbei, weil `install.sh` dort bereits deaktiviert hat.
- **Fail-safe**, soweit nicht optisch (Stufe 3, Punkt 6): Rückgabewert, gestoppter Client, kein Neustart in der Schleife. Nur das Fehlerfenster selbst braucht einen Menschen.

## Phase 3 — Review

Code-Review durch eine zweite Claude-Instanz, danach Sichtung und Abarbeitung der Befunde. Vorbedingung ist, dass Code und Doku nirgends mehr auseinanderklaffen — sonst verbraucht das Review seine Aufmerksamkeit für Bekanntes.

## Phase 4 — Übernahme in den Hauptpfad

Echter Merge nach `dev` mit vollständiger Historie, ausdrücklich kein Squash.

## Phase 5 — Abnahme von Hand

Stufe 3 auf dem Zielrechner, beschrieben in der Implementierungsdoku unter „Stufe 3: Abnahme von Hand". Nach dem Umzug aus Phase 2 bleiben sieben Punkte.

Punkt 9 darin ist die **einzige inhaltlich offene Annahme** des ganzen Vorhabens: Die genaue JSON-Struktur von `urbackupclientctl status` konnte nicht verifiziert werden, weil das Client-Backend beim Programmieren nicht lief. Der Parser deckt beide plausiblen Formen ab und fällt sonst geordnet auf „nicht erreichbar" zurück — ob die Zahlen stimmen, zeigt erst die erste echte Sicherung. Durch keinen Test ersetzbar, und damit der eigentliche Schlusspunkt.
