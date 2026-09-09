# Roadmap

1. Offene Punkte klären:

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
