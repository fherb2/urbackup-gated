# Roadmap

## 1 Vorgeschriebenes Verhalten ohne Prüfung

Vier Festlegungen der Implementierungsdoku, die im Code umgesetzt, aber von keiner der drei Prüfstufen abgedeckt sind. Jeder Eintrag nennt die Stelle, die ihn vorschreibt — daran ist später erkennbar, dass es um die Absicherung einer Vorgabe geht und nicht um einen nachträglichen Einfall.

- **`yad`-Prüfung beim Dienststart.** Der Dienst prüft bei seinem Start, ob `yad` vorhanden ist, und schreibt dessen Fehlen ins Journal. Vorgeschrieben in „Folge daraus, die beim Programmieren nicht untergehen darf" — die Doku markiert diesen Punkt selbst als einen, der nicht untergehen darf.
- **Alter der Statusangabe.** Das Kommandozeilenwerkzeug zeigt an, wie lange das letzte Schreiben der Datei her ist. Vorgeschrieben in „Zustand, Merken zwischen Aufrufen und Statusabfrage", dritter Verwendungszweck der Sammelfunktion.
- **Ablehnung einer unverstandenen `schema_version`.** Das Werkzeug soll eine Datei, die es nicht versteht, ablehnen statt sie falsch anzuzeigen. Vorgeschrieben in „Schema von `state.json`". Geprüft wird heute nur, dass die Version geschrieben wird — nie, dass eine falsche zurückgewiesen wird.
- **Blockierender Notify-Aufruf.** Er darf die Prüfschleife nicht anhalten, weshalb er in einem eigenen Thread läuft. Vorgeschrieben in „Konsequenz für die Umsetzung: Da dieser Aufruf blockiert…". Der Container-Stub für `notify-send` kehrt sofort zurück, blockiert also nie — der Fall wird von keiner Stufe erzeugt.

## 2 Abnahme von Hand

Stufe 3 der Prüfung, neun Punkte, beschrieben in der Implementierungsdoku unter „Stufe 3: Abnahme von Hand". Sie steht aus, bis das Werkzeug auf dem Zielrechner installiert ist.

Punkt 9 darin ist die **einzige inhaltlich offene Annahme** der Implementierung: Die genaue JSON-Struktur von `urbackupclientctl status` konnte nicht verifiziert werden, weil das Client-Backend beim Programmieren nicht lief. Der Parser deckt beide plausiblen Formen ab und fällt sonst geordnet auf „nicht erreichbar" zurück — ob die Zahlen stimmen, zeigt erst die erste echte Sicherung.

## 3 Zwei Abnahmepunkte, die ohne Desktop automatisierbar wären

Stufe 3 begründet sich damit, dass sie einen Menschen an einem echten Desktop braucht. Auf zwei ihrer Punkte trifft das nicht zu; sie liefen im Container:

- **Selbstheilung** (Punkt 7): `systemctl enable urbackupclientbackend`, Dienst neu starten, prüfen dass er wieder deaktiviert ist. Braucht weder Anzeige noch Funkgerät. Der Container prüft das heute auch nicht nebenbei mit — dort hat `install.sh` bereits deaktiviert, der Zweig läuft nie durch.
- **Fail-safe** (Punkt 6), soweit nicht optisch: Rückgabewert 78, Client gestoppt, kein Neustart in der Schleife. Nur das Fehlerfenster selbst braucht einen Menschen.

Offen als Entscheidung, nicht als Aufgabe: ob das umgezogen wird oder in Stufe 3 bleibt.
