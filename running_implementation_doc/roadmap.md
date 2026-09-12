# Roadmap

Drei Phasen bis zur Abnahme. Alles, was den Code noch verändert, liegt vor dem Review; alles, was den Nutzer an den Rechner bindet, dahinter.

## Phase 1 — Review

Code-Review durch eine zweite Claude-Instanz, danach Sichtung und Abarbeitung der Befunde.

Vorbedingung ist, dass Code und Doku nirgends mehr auseinanderklaffen — sonst verbraucht das Review seine Aufmerksamkeit für Bekanntes. Ein Abgleich Kapitel für Kapitel gegen den Code hat diese Vorbedingung hergestellt; die dabei gefundenen Abweichungen sind beseitigt.

## Phase 2 — Übernahme in den Hauptpfad

Echter Merge nach `dev` mit vollständiger Historie, ausdrücklich kein Squash. Vorher der Push der Werkbank.

## Phase 3 — Abnahme von Hand

Stufe 3 auf dem Zielrechner, beschrieben in der Implementierungsdoku unter „Stufe 3: Abnahme von Hand". Acht Punkte, alle auf das beschränkt, was ein Auge oder ein echtes Funkgerät braucht: die Erscheinung der Meldungen und des Live-Fensters auf diesem Desktop, ein echter Netzwechsel, die Dockingstation-Strenge, die Handschalter, das Fehlerfenster des Fail-safe und das Verhalten beim Abmelden.

Punkt 8 darin ist die **einzige inhaltlich offene Annahme** des ganzen Vorhabens: Die genaue JSON-Struktur von `urbackupclientctl status` konnte nicht verifiziert werden, weil das Client-Backend beim Programmieren nicht lief. Der Parser deckt beide plausiblen Formen ab und fällt sonst geordnet auf „nicht erreichbar" zurück — ob die Zahlen stimmen, zeigt erst die erste echte Sicherung. Durch keinen Test ersetzbar, und damit der eigentliche Schlusspunkt.
