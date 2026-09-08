# Roadmap

1. Offene Punkte klären:

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
