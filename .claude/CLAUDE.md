# Projektspezifische Festlegungen: urbackup-gated

Diese Datei ergänzt die globale `~/.claude/CLAUDE.md` und überschreibt sie dort,
wo sie ihr widerspricht. Sie enthält **ausschließlich** Abweichendes und
Zusätzliches — keine Kopie der allgemeinen Regeln.

## Schritte, Commits und Freigaben

**Ein Schritt ist die Einheit der Freigabe: ein Plan, eine Zustimmung.**
**Ein Commit ist die Einheit der Lösung: genau ein behobenes Problem je Commit.**

Ein Schritt umfasst deshalb in der Regel mehrere Commits. So bleibt in der
Historie nachvollziehbar, was womit gelöst wurde, ohne dass für jede
Kleinigkeit ein eigener Plan vorgelegt und einzeln freigegeben werden muss.

Wer mehrere Lösungen versehentlich in einen Commit legt, teilt ihn wieder auf,
solange er nicht veröffentlicht ist — das ist in dieser Sitzung einmal nötig
gewesen.

## Jede neue Prüfung wird belegt

**Eine neu geschriebene Prüfung gilt erst als fertig, wenn gezeigt ist, dass sie
den Fehler auch fängt, gegen den sie geschrieben wurde.** Verfahren: Den Code
auf einer Kopie absichtlich zurückdrehen und den Lauf wiederholen. Die Prüfung
muss rot melden, und zwar sie selbst — nicht bloß irgendeine.

Das ist keine Formalie. In dieser Sitzung hat dieses Verfahren fünf eigene
Fehler gefunden, die alle grün ausgesehen hatten:

- eine Prüfung, die unter `set -u` nicht rot meldete, sondern die ganze Suite
  abbrach — sichtbar nur im Fehlerfall,
- Szenarien, die alte und neue Logik gar nicht unterschieden,
- eine Attrappe, die unabhängig von den angeforderten Feldern antwortete,
  wodurch die Feldwahl ungeprüft blieb,
- eine Mutation, die die falsche Stelle traf und dadurch zu Unrecht als
  „nicht gefangen" erschien,
- eine Prüfung, die an einer Stelle stand, an der die Bedingung des Fehlers noch
  gar nicht galt.

**Der letzte Punkt ist der häufigste Fehlertyp in diesem Projekt:** Die Prüfung
existiert, ist grün, und steht dort, wo das Geprüfte nicht eintreten kann.
Bei jeder neuen Prüfung deshalb ausdrücklich fragen: *Gilt die Bedingung an
dieser Stelle im Ablauf überhaupt schon?*

## Prüfen heißt: gegen die Vorgabe, nicht gegen eigene Maßstäbe

**Geprüft wird gegen die Aufgabenbeschreibung und die Implementierungsdoku.**
Nicht gegen Anforderungen, die beim Prüfen plausibel erscheinen, aber nirgends
vereinbart sind.

Ein Befund braucht eine Fundstelle: Welche Festlegung wird verletzt, und wo
steht sie? Fehlt die Fundstelle, ist es kein Befund, sondern ein Vorschlag —
und als solcher zu kennzeichnen. Konstruierte Sonderfälle sind keine Befunde.

Grund: Der Nutzer kann einen Bericht nur beurteilen, wenn der Maßstab derselbe
ist, auf den er sich eingelassen hat. Ein Bericht gegen erfundene Kriterien
kostet ihn die Zeit, jeden einzelnen Punkt zurückzuweisen — und untergräbt das
Vertrauen in die Punkte, die stimmen.

## Umgebung

`.claude/` wird **mitversioniert** (siehe 1.2 global): Es wird zwischen mehreren
Rechnern gearbeitet. Beim Schreiben hierher jedes Mal prüfen, dass die
`.gitignore` nichts davon ausschließt.

In der **globalen** `~/.claude/settings.json` steht `Bash(docker *)` unter
`permissions.deny`. Direkte Docker-Aufrufe werden dadurch abgewiesen; die
Container-Prüfstufe läuft nur, weil `tests/container/run.sh` unter eigenem Namen
startet. Für Diagnose an Images oder Containern muss der Nutzer die Regel
lockern — das ist seine Datei, sie wird nicht von hier aus geändert.
