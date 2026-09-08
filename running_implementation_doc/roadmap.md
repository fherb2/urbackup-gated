# Roadmap

1. Offene Punkte klären:

   - **Startreihenfolge/Alleinzuständigkeit.** Damit der eigentliche
     `urbackupclientbackend`-Dienst nicht kurz vor `urbackup-gated` hochkommt
     und dann sofort wieder gestoppt wird (kurzes Flackern beim Boot), sollte
     `urbackupclientbackend.service` selbst aus dem automatischen
     Systemstart herausgenommen werden (`systemctl disable`, nicht `mask`,
     damit `urbackup-gated` ihn weiterhin gezielt starten kann) —
     `urbackup-gated` wird dann die einzige Instanz, die ihn je startet oder
     stoppt. `urbackup-gated` selbst bekäme `Before=urbackupclientbackend.service`
     und `After=NetworkManager.service` / `Wants=NetworkManager.service`.

   - **Rechte-Trennung für Notify.** `systemctl start/stop` braucht
     Root-Rechte, Desktop-Notifications müssen aber in die angemeldete
     Desktop-Sitzung (D-Bus-Session-Bus) zugestellt werden — beides in einem
     als root laufenden Dienst zu vereinen ist technisch nicht trivial.
     Übliche Lösungen: der Dienst läuft als root und ruft für die
     Notify-Zustellung gezielt in die Nutzersitzung hinein (`sudo -u
     herbrand DBUS_SESSION_BUS_ADDRESS=... notify-send ...`, Adresse
     ermittelbar über `/run/user/<uid>/bus`), oder der Dienst läuft von
     vornherein im User-Kontext als `systemd --user`-Dienst und nutzt für
     die eigentlichen `systemctl start/stop`-Aufrufe eine eng gefasste
     `sudoers`-Freigabe nur für genau diese zwei Befehle. Muss vor der
     Implementierung entschieden werden.

   - **Verhalten bei laufender Sicherung und Netzwechsel ins Verbotene.**
     Wenn während einer aktiven Sicherung die WLAN-SSID wechselt oder die
     Verbindung getrennt wird (z. B. Wechsel vom erlaubten Netz zum
     Hotspot) — sofort hart stoppen (Sicherung wird unterbrochen, UrBackup
     fängt später neu/fortgesetzt an) oder erst nach der laufenden
     Sicherung stoppen? Reine Sicherheitsfrage fürs Datenvolumen spricht
     für sofort hart stoppen.

   - **Fail-safe bei fehlender/kaputter Konfiguration.** Fehlt
     `/etc/urbackup-gated` oder ist sie nicht lesbar/fehlerhaft: Vorschlag,
     dann grundsätzlich **nicht** zu starten (sicherer Default), statt
     UrBackup ungeprüft laufen zu lassen.

   - **Testbarkeit.** Ein Kommandozeilen-Modus, der nur anzeigt, was der
     Dienst jetzt täte (starten/stoppen/nichts), ohne es auszuführen —
     nützlich, um die SSID-Logik zu prüfen, bevor man sich live darauf
     verlässt.

   - **Protokollierung.** Normale Log-Ausgabe auf stdout/stderr, damit sie
     im systemd-Journal landet (`journalctl -u urbackup-gated`) — kein
     eigenes Logfile nötig.

2. Fixierung: Konzept wird schrittweise zu verbindlichen Vorgaben.
3. Segmentierung in die dreigeteilte Implementierungsdoku (zusammengefasst in
   einem Dokument: Kapitel 1 Zusammenhänge, 2 Vorgaben, 3 Einheiten, plus
   Anhang) — über den `/segmentierung`-Skill, sobald das Konzept dafür reif
   ist.
4. Implementierung inkl. `install.sh`/`uninstall.sh` und README, nach dem
   Vorbild der UrBackup-eigenen Installationsskripte.
