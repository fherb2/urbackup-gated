# Roadmap

1. Fixierung: Konzept wird schrittweise zu verbindlichen Vorgaben.
2. Segmentierung in die dreigeteilte Implementierungsdoku (zusammengefasst in
   einem Dokument: Kapitel 1 Zusammenhänge, 2 Vorgaben, 3 Einheiten, plus
   Anhang) — über den `/segmentierung`-Skill, sobald das Konzept dafür reif
   ist.

   Vorwissen zu diesem Punkt — zwei bereits getroffene Entscheidungen, die
   ihrer Natur nach nach Segment 2 gehören und dort beim Segmentieren
   einzusortieren sind, statt sie vorher provisorisch in Kapitel 1 abzulegen:

   - **Konfigurationsformat: TOML** in `/etc/urbackup-gated.conf` (Endung
     bleibt `.conf`, Inhalt ist TOML). Gelesen per `tomllib` aus der
     Standardbibliothek, vorhanden seit Python 3.11 und auf diesem Rechner
     geprüft (Python 3.12.3); nur lesend, geschrieben wird die
     Konfiguration nie. Ausschlaggebend war die SSID-Liste: JSON kennt keine
     Kommentare und die Datei wird von Hand gepflegt; YAML wäre eine
     zusätzliche Abhängigkeit; INI mit `configparser` kennt keine Listen, man
     müsste an Kommas trennen — und SSIDs dürfen Kommas, Leerzeichen und
     Anführungszeichen enthalten, wodurch es irgendwann still falsch würde.
     TOML hat echte Zeichenketten-Arrays mit sauberer Quotierung, dazu
     Kommentare und getypte Zahlen für die Intervalle. Schlüssel englisch wie
     aller Code: `allowed_ssids` als Array, dazu eine Gruppe für die
     Intervalle (Prüftakt regulär und bei offenem Statusfenster, Abstand der
     Ruhemeldung, Abstand der Fortschrittsmeldung) und eine für die
     Anzeigedauer der Notifications.
   - **Schema von `state.json`**: `schema_version` (damit das Statuswerkzeug
     eine Datei, die es nicht versteht, ablehnen kann statt sie falsch
     anzuzeigen), `written_at` als ISO-8601-Zeitstempel mit Zeitzone (daraus
     berechnet das Statuswerkzeug das geforderte Alter), `network` mit der
     Liste aller aktiven Verbindungen (Typ, Name, bei WLAN die SSID samt
     Kennzeichen „erlaubt") plus den abgeleiteten Wahrheitswerten
     „überhaupt eine Verbindung vorhanden" und „nicht erlaubtes WLAN aktiv",
     `decision` mit den drei getrennten Wahrheitswerten `network_allows`,
     `user_enabled` und dem verundeten `effective` sowie `reason` als
     fertigem, menschenlesbarem Satz, und `urbackup_client` mit Unit-Zustand,
     Serververbindung, laufender Sicherung und den Fortschrittsfeldern.
     Wichtigster Entwurfspunkt darin ist `decision.reason`: Der
     Begründungstext entsteht **einmal** in der Sammelfunktion und wird von
     Notification, Statusfenster und Kommandozeilenwerkzeug gleichermaßen
     verwendet — sonst entstehen drei Stellen, die dasselbe in leicht
     verschiedenen Worten sagen und mit der Zeit auseinanderlaufen.
     Geschrieben wird die Datei atomar wie die Kommandodatei.
3. Implementierung inkl. `install.sh`/`uninstall.sh` und README, nach dem
   Vorbild der UrBackup-eigenen Installationsskripte.
