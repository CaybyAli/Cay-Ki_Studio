# Cay Studio 0.18.0 – so geht es weiter

## Update installieren

1. ZIP laden, Rechtsklick → **Alle extrahieren** → in einen **neuen** Ordner.
2. Läuft eine Produktion: **Pausieren** oder fertig werden lassen. Hängt ein Abschnitt: **erst den PC neu starten**.
3. **Cay_Studio_Update.cmd** doppelklicken, auf **CAY STUDIO 0.18.0 INSTALLIERT** warten. Kein PC-Neustart nötig.
4. Im Browser **Strg + F5**. Unten muss **0.18.0** stehen.

Der Installer sichert die Datenbank. Startet die neue Version nicht, kehrt er selbst zur vorherigen zurück. Projekte, Bilder, Stimmen und fertige Filme bleiben erhalten.

Starte danach kein älteres Update mehr. Ab 0.18 verweigert das Update-Programm das selbst, die alte 0.17-Datei kann das noch nicht. Projekte aus 0.18 laufen nur mit 0.18 (ist es doch passiert, starte einfach das 0.18-Update noch einmal, es geht nichts verloren).

## Das neue Studio

- **Neu:** Idee eintippen, Länge, Folgen, Look und Qualität wählen. **Autopilot** an = ohne Zwischenstopps fertig. Oder **Mein Drehbuch**: dein eigenes Drehbuch wortgetreu verfilmen (siehe unten).
- **Projekte:** Alles, was auf dich wartet, steht vorn. Jedes Projekt zeigt genau einen nächsten Schritt und die echte Rechenzeit.
- **Figuren (Reiter):** Deine Figuren-Bibliothek. Bild und Stimme einmal festlegen, in jedem Film wiederverwenden, auch in einem laufenden Projekt (tippe dort auf die Figur).
- **Fertige Filme** liegen im jeweiligen Projekt: ansehen, herunterladen, Beschreibung kopieren. Mit Titelbild gibt es zusätzlich `Cover_<Film>.png`.
- **Lautstärke:** Musik, Geräusche und Umgebung per Regler beim Ton. Bei einem fertigen Film: **Lautstärke und Ton ändern**. Der Autopilot wartet dann auf deine Freigabe.
- **Titelbild:** Beim Anlegen unter „Figuren, Look-Vorlagen, Titelbild und Musik“: am Anfang, nach dem Einstieg oder aus.
- **Look-Vorlagen:** Unter „Figuren, Look-Vorlagen und Musik“ bis zu vier Bilder hochladen (JPG, PNG, WebP). Sie bestimmen nur den Stil. Personen daraus kommen nicht in den Film.
- **Figuren:** Jede Figur wird einmal gestaltet und in allen Szenen genau so verwendet. Bekannte Figuren wie SpongeBob werden als Original angelegt. Am sichersten: bei der Figur ein eigenes Bild hochladen.
- **Deine Figuren:** Bei der Bildauswahl siehst du oben jede Figur. **Neu gestalten** zeichnet die Figur und alle Szenen mit ihr neu.
- **Ziel des Films:** Steht über dem Drehbuch: Haken, Wendung, Pointe.
- **Drehbuch:** Die KI schreibt den Film als durchgehendes Gespräch, prüft Wortzahl und Sprecherwechsel und überarbeitet es einmal. Über dem Drehbuch steht eine Prüfzeile: Wörter, Einstellungen, stumme Aktionen, später Sprachanteil und längste Pause.
- **Figuren vorher zeigen:** Ein kurzer Stopp vor den Szenenbildern, auch mit Autopilot. „Neu gestalten“ oder „Eigenes Bild“, dann „Figuren passen, weiter“. Abschaltbar beim Anlegen.
- **Zahnrad oben rechts:** Einrichtung prüfen, **Turbo einrichten**, Stimmen und Animation einrichten, **Benachrichtigungen**, Figurentausch und bisherige Oberfläche.

## Mein Drehbuch

Du hast schon ein fertiges Drehbuch? Oben bei **Neu** auf **Mein Drehbuch** tippen, den Text einfügen oder eine **.md**- oder **.txt**-Datei wählen. Das Studio spricht jeden Satz genau so, wie er dasteht. Die KI liest dein Drehbuch, weiß dadurch, was passiert, und gestaltet nur Figuren, Bilder und Bewegung dazu. Sie ändert keinen Satz und erfindet keine Handlung.

Unter dem Textfeld steht sofort, was das Studio liest: Figuren, Szenen, Sätze, Wörter, Folgen und die **Länge nach Drehbuch** (mindestens 15 Sekunden, bis 3 Minuten pro Folge). Probleme stehen mit Zeilennummer da. Unter „Figuren, Look-Vorlagen, Titelbild und Musik“ kannst du jeder Figur aus dem Drehbuch ein eigenes Bild, eine eigene Stimme oder ein Profil aus deinen Figuren geben. **Vorlage herunterladen** zeigt ein fertiges Beispiel.

So schreibst du es:

```
# Der verschwundene Kuchen
FIGUR: Oma Hilde – 72 Jahre, Schürze, streng, aber herzlich
### Szene 1 – Küche – Oma steht vor dem leeren Teller
OMA HILDE (wütend): Wer hat meinen Kuchen gegessen?
TIM [ängstlich]: Ich war's nicht, ehrlich!
AKTION: Tim versteckt die Hände hinter dem Rücken.
```

Für eine Serie: Überschriften `## Folge 1: Titel`, `## Folge 2: Titel`. Sprechhaltungen: ruhig, fröhlich, begeistert, wütend, schreiend, ängstlich, panisch, traurig, flüsternd, drohend, spöttisch, überrascht, triumphierend, flehend, genervt, verwirrt. Was im Satz in Klammern steht, wird nicht gesprochen. Eine PDF-Datei kann das Studio nicht zuverlässig lesen: Text im PDF kopieren und einfügen oder als .txt speichern.

## Benachrichtigungen aufs Handy

Zahnrad → **Benachrichtigungen**. Am einfachsten mit **Telegram**: In Telegram **@BotFather** öffnen, **/newbot** senden, Namen wählen, den Schlüssel ins Studio kopieren, beim eigenen Bot **Start** tippen, „Verbindung prüfen“. Kostenlos. Das Studio meldet sich, wenn ein Film fertig ist, wenn es auf dich wartet oder anhält. Die Anrede („Sir Cay“) ist änderbar. Telegram speichert die Nachrichten auf seinen Servern.

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
