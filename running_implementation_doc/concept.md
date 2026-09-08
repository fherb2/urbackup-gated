# Konzept: Netzwerk-gesteuerter Start/Stopp des UrBackup-Clients

Status: Findungsphase — offenes Konzipieren, nichts hier ist festgelegt.

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

## Zustand und Merken zwischen Aufrufen

Vorschlag zur Diskussion, abweichend von der ursprünglichen Idee (UUID-Datei unter
`/tmp`): Ein fester, bekannter Pfad unter `/run/urbackup-watcher/state.json` (oder
zum gewählten Dienstnamen passend). `/run` ist per Definition ein tmpfs und wird bei
jedem Neustart automatisch geleert — das erfüllt genau den gewünschten Zweck
("Datei weg = Ausgangslage klar nach Neustart"), ist aber unter einem festen,
auffindbaren Namen leichter zu debuggen als eine zufällige UUID-Datei, die man beim
Fehlersuchen erst wiederfinden müsste.

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
(JSON-Ausgabe). Die relevanten Felder kennen wir bereits aus dieser Woche:
`internet_connected`, `servers[]`, `running_processes[]` (darin u. a. `percent_done`,
`eta_ms`).

## Konfiguration

Eigene Datei/Ordner: `/etc/urbackup-gated`. Muss mindestens enthalten: Liste erlaubter SSIDs,
Anzeigedauer der Notify-Meldungen, ggf. die beiden Intervalle (2 h / 15 min), falls
sie einstellbar sein sollen statt fest im Code.

Aktuell genannte SSIDs: `lieluX`, `lielux`, `lieluxVPN`, `HZDR` — **geklärt:** kein
Tippfehler, `lieluX` und `lielux` sind zwei tatsächlich unterschiedliche, echte
Netze. Vergleich bleibt case-sensitiv.

## Festgelegt

1. **Dienstname: `urbackup-gated`.** Kürzer als der ursprüngliche Arbeitstitel
   `urbackup-watcherd`, folgt aber weiterhin der üblichen Konvention, dass ein
   Dämon mit einem `d` am Ende benannt wird. Systemd-Unit entsprechend
   `urbackup-gated.service`, Konfigurationsordner-Arbeitstitel damit
   `/etc/urbackup-gated` (statt bisher `/etc/urbackup-watcher`).

## Offene Punkte / Vorschläge zur Diskussion (noch keine Festlegung)

2. **Startreihenfolge/Alleinzuständigkeit.** Damit der eigentliche
   `urbackupclientbackend`-Dienst nicht kurz vor dem Watcher hochkommt und dann
   sofort wieder gestoppt wird (kurzes Flackern beim Boot), sollte
   `urbackupclientbackend.service` selbst aus dem automatischen Systemstart
   herausgenommen werden (`systemctl disable`, nicht `mask`, damit der Watcher ihn
   weiterhin gezielt starten kann) — der Watcher wird dann die einzige Instanz, die
   ihn je startet oder stoppt. Der Watcher-Dienst selbst bekäme
   `Before=urbackupclientbackend.service` und `After=NetworkManager.service` /
   `Wants=NetworkManager.service`.

3. **Rechte-Trennung für Notify.** `systemctl start/stop` braucht Root-Rechte,
   Desktop-Notifications müssen aber in Deine angemeldete Desktop-Sitzung
   (D-Bus-Session-Bus) zugestellt werden — beides in einem als root laufenden
   Dienst zu vereinen ist technisch nicht trivial. Übliche Lösungen: der Dienst
   läuft als root und ruft für die Notify-Zustellung gezielt in die Nutzersitzung
   hinein (`sudo -u herbrand DBUS_SESSION_BUS_ADDRESS=... notify-send ...`, Adresse
   ermittelbar über `/run/user/<uid>/bus`), oder der Dienst läuft von vornherein im
   User-Kontext als `systemd --user`-Dienst und nutzt für die eigentlichen
   `systemctl start/stop`-Aufrufe eine eng gefasste `sudoers`-Freigabe nur für genau
   diese zwei Befehle. Muss vor der Implementierung entschieden werden.

4. **Verhalten bei laufender Sicherung und Netzwechsel ins Verbotene.** Wenn
   während einer aktiven Sicherung die WLAN-SSID wechselt oder die Verbindung
   getrennt wird (z. B. Du gehst vom erlaubten Netz an den Hotspot) — sofort hart
   stoppen (Sicherung wird unterbrochen, UrBackup fängt später neu/fortgesetzt an,
   wie wir diese Woche gesehen haben), oder erst nach der laufenden Sicherung
   stoppen? Reine Sicherheitsfrage fürs Datenvolumen spricht für sofort hart
   stoppen — das würde ich vorschlagen, aber das ist Deine Entscheidung.

5. **Fail-safe bei fehlender/kaputter Konfiguration.** Fehlt `/etc/urbackup-watcher`
   oder ist sie nicht lesbar/fehlerhaft: Vorschlag, dann grundsätzlich **nicht** zu
   starten (sicherer Default), statt UrBackup ungeprüft laufen zu lassen.

6. **Testbarkeit.** Ein Kommandozeilen-Modus, der nur anzeigt, was der Dienst jetzt
   täte (starten/stoppen/nichts), ohne es auszuführen — nützlich, um die
   SSID-Logik zu prüfen, bevor man sich live darauf verlässt.

7. **Protokollierung.** Normale Log-Ausgabe auf stdout/stderr, damit sie im
   systemd-Journal landet (`journalctl -u <dienstname>`) — kein eigenes Logfile
   nötig, passt zum Rest des Systems.

## Technische Bausteine (grobe Skizze, keine Festlegung)

- Sprache: Python (wie gewünscht).
- Netzwerk-Ereignisse: NetworkManager-Dispatcher-Skript unter
  `/etc/NetworkManager/dispatcher.d/`, das den laufenden Watcher-Dienst antriggert
  (z. B. per Signal oder D-Bus-Aufruf), plus eigener 30-Sekunden-Timer im Dienst
  selbst als Fallback.
- Aktuelle SSID/Verbindungsart ermitteln: `nmcli` (Kommandozeile) oder direkt über
  die NetworkManager-D-Bus-API.
- Notify: `notify-send` (aus `libnotify-bin`) per Subprozess, oder eine
  Python-D-Bus-Bibliothek — einfacher Subprozess-Aufruf ist vermutlich robuster
  und hat weniger Abhängigkeiten.

## Weiteres Vorgehen

Siehe `roadmap.md` im selben Ordner.
