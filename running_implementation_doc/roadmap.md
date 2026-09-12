# Roadmap

Die Nacharbeit aus dem Code-Review vom 12. September 2026 ist abgeschlossen. Was bleibt, sind zwei Schritte, die nicht mehr am Code hängen.

## Phase 1 — Übernahme in den Hauptpfad

Push der Werkbank, dann echter Merge nach `dev` mit vollständiger Historie, ausdrücklich kein Squash.

## Phase 2 — Abnahme von Hand

Stufe 3 auf dem Zielrechner, beschrieben in der Implementierungsdoku unter „Stufe 3: Abnahme von Hand". Acht Punkte, alle auf das beschränkt, was ein Auge oder ein echtes Funkgerät braucht.

**Zusätzlich mitzuprüfen, seit die Unit an `graphical-session.target` hängt:** dass der Dienst mit der grafischen Sitzung startet und mit ihr endet — und dass er sich in einer reinen SSH-Sitzung gar nicht erst meldet.

Punkt 8 ist die **einzige inhaltlich offene Annahme** des ganzen Vorhabens: Die genaue JSON-Struktur von `urbackupclientctl status` konnte nicht verifiziert werden, weil das Client-Backend beim Programmieren nicht lief. Ob die Zahlen stimmen, zeigt erst die erste echte Sicherung. Durch keinen Test ersetzbar, und damit der eigentliche Schlusspunkt.

## Offen, ohne Termin

**Ein Prüfpunkt war einmal rot und im nächsten Lauf wieder grün:** „without any connection the running client is left alone". Die Ursache ist **ungeklärt**. Ein gestorbener Dienst sähe genauso aus und ließe jede folgende Prüfung grün — deshalb sagt der Prüfpunkt jetzt im Fehlerfall, ob der Dienst noch läuft, und gibt sein Protokoll aus. Tritt es wieder auf, ist die Antwort da.

**Das Container-Abbild `urbackup-gated-tests`** liegt nach den Prüfläufen mit `KEEP_IMAGE=1` noch auf dem Rechner — einige hundert Megabyte. Nach der Abnahme kann es weg: `docker image rm urbackup-gated-tests`, oder ein Lauf ohne `KEEP_IMAGE`.

**Zwei echte Netznamen stehen weiterhin im öffentlichen Repository:** `lieluX` und `lielux` in der Implementierungsdoku als Begründung dafür, warum der Vergleich case-sensitiv bleibt, und `lieluX` in den Testszenarien. Aus der ausgelieferten Konfiguration sind sie entfernt. Ob das genügt, ist eine Entscheidung, keine Aufgabe.
