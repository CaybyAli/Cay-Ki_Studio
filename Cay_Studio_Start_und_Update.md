# Cay Studio 0.17.0 – so geht es weiter

## Update installieren

1. ZIP laden, Rechtsklick → **Alle extrahieren** → in einen **neuen** Ordner.
2. Läuft eine Produktion: **Pausieren** oder fertig werden lassen. Hängt ein Abschnitt: **erst den PC neu starten**.
3. **Cay_Studio_Update.cmd** doppelklicken, auf **CAY STUDIO 0.17.0 INSTALLIERT** warten.
4. **PC einmal neu starten** (die schnellere Lippen-Animation lädt erst beim Neustart von ComfyUI), dann **Cay_Studio_Starten.cmd**.
5. Im Browser **Strg + F5**. Unten muss **0.17.0** stehen.

Der Installer sichert die Datenbank. Startet die neue Version nicht, kehrt er selbst zur vorherigen zurück. Projekte, Bilder, Stimmen und fertige Filme bleiben erhalten.

## Das neue Studio

- **Neu:** Idee eintippen, Länge, Folgen, Look und Qualität wählen. **Autopilot** an = ohne Zwischenstopps fertig.
- **Projekte:** Alles, was auf dich wartet, steht vorn. Jedes Projekt zeigt genau einen nächsten Schritt.
- **Fertige Filme** liegen im jeweiligen Projekt: ansehen, herunterladen, Beschreibung kopieren.
- **Look-Vorlagen:** Unter „Figuren, Look-Vorlagen und Musik“ bis zu vier Bilder hochladen (JPG, PNG, WebP). Sie bestimmen nur den Stil. Personen daraus kommen nicht in den Film.
- **Figuren:** Jede Figur wird einmal gestaltet und in allen Szenen genau so verwendet. Bekannte Figuren wie SpongeBob werden als Original angelegt. Am sichersten: bei der Figur ein eigenes Bild hochladen.
- **Deine Figuren:** Bei der Bildauswahl siehst du oben jede Figur. **Neu gestalten** zeichnet die Figur und alle Szenen mit ihr neu.
- **Ziel des Films:** Steht über dem Drehbuch: Haken, Wendung, Pointe.
- **Drehbuch:** Die KI schreibt den Film als durchgehendes Gespräch, prüft Wortzahl und Sprecherwechsel und überarbeitet es einmal. Über dem Drehbuch steht eine Prüfzeile: Wörter, Einstellungen, stumme Aktionen, später Sprachanteil und längste Pause.
- **Figuren vorher zeigen:** Ein kurzer Stopp vor den Szenenbildern, auch mit Autopilot. „Neu gestalten“ oder „Eigenes Bild“, dann „Figuren passen, weiter“. Abschaltbar beim Anlegen.
- **Zahnrad oben rechts:** Einrichtung prüfen, **Turbo einrichten**, Stimmen und Animation einrichten, Figurentausch und bisherige Oberfläche.

## Turbo

Einmal im Zahnrad **Turbo einrichten**. Das Studio installiert eine schnellere Rechenart und prüft sie auf deiner Grafikkarte. Danach **PC neu starten**. Schlägt ein Abschnitt mit Turbo fehl, schaltet sich Turbo selbst ab und „Fortsetzen“ rechnet ohne Turbo weiter.

## Qualität

| Qualität | Bildgröße | Wofür |
| --- | --- | --- |
| Entwurf | 480×832 | Ideen schnell ausprobieren, etwa halbe Rechenzeit |
| Standard | 576×1024 | Die Qualität deines Keks-Films |

Die Rechenzeit-Schätzung auf der Startseite stammt aus deiner Messung vom 12.10. Sie ist eine Hochrechnung.

## Wenn etwas anhält

Das Projekt zeigt oben, was passiert ist, und den passenden Knopf: **Fortsetzen**, **Neu planen**, **Abschnitt neu starten** oder **Neue Fassung planen**. **Fehlerbericht speichern** hilft mir bei der Ursache.

## Nach einem PC-Neustart

**Cay_Studio_Starten.cmd** doppelklicken. Falls kein Browser aufgeht: **http://127.0.0.1:8787**.

## Diagnose

**Cay_Studio_Diagnose.cmd** liest deine neuesten Projekte mit Zeittabelle aus und schreibt **Cay_Studio_Diagnose.txt**. Es ändert nichts.

Plan, Messwerte und ehrliche Grenzen: **CAY_STUDIO_PLAN.md**.
