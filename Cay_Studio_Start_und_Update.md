# Cay Studio 0.19.1 – so geht es weiter

## Update installieren

1. ZIP laden, Rechtsklick → **Alle extrahieren** → in einen **neuen** Ordner.
2. Läuft eine Produktion: **Pausieren** oder fertig werden lassen. Hängt ein Abschnitt: **erst den PC neu starten**.
3. **Cay_Studio_Update.cmd** doppelklicken, auf **CAY STUDIO 0.19.1 INSTALLIERT** warten. Kein PC-Neustart nötig.
4. Im Browser **Strg + F5**. Unten muss **0.19.1** stehen.

Der Installer sichert die Datenbank. Startet die neue Version nicht, kehrt er selbst zur vorherigen zurück. Projekte, Bilder, Stimmen und fertige Filme bleiben erhalten.

Starte danach kein älteres Update mehr. Ab 0.18 verweigert das Update-Programm das selbst, die alte 0.17-Datei kann das noch nicht. Projekte aus 0.18 laufen nur mit 0.18 (ist es doch passiert, starte einfach das 0.18-Update noch einmal, es geht nichts verloren).

## Neu in 0.19.0

Alles Neue gilt nur für **neue Projekte**. Alte Projekte bleiben genau so, wie sie sind. Für eine alte Idee: Projekt öffnen → **Neue Fassung planen**.

- **Kein Export-Stopp mehr nach Stunden:** Die Meldung „Bildlänge oder Bildgröße stimmt nicht“ kam von winzigen Bildlücken beim Schneiden. Ein angehaltenes Projekt mit dieser Meldung: öffnen, **Fortsetzen**.
- **Ton:** kein Rauschen mehr am Anfang stummer Einstellungen, jede Stimme gleich laut (auch eine leise Stimmprobe), sanftes Entrauschen, Musik deutlich unter der Sprache, ein ruhiger, durchgehender Hintergrund pro Ort.
- **Stimmen:** hochgeladene Stimmproben werden vor dem Klonen gereinigt (das Original bleibt), jede Zeile in 2–3 Aufnahmen, das Studio nimmt die lebendigste. Wörter in Großbuchstaben wie „DIR“ werden normal gesprochen, Abkürzungen wie USA bleiben.
- **Bild:** wechselnde Kamerawinkel (Großaufnahme, Untersicht, über die Schulter …), Kamerafahrt bei jeder Sprechszene, Action ohne Zeitlupe.
- **Tempo:** Die Lippen-Animation rechnet nur noch so viele Bilder, wie die Szene braucht. Keine Leerlauf-Pausen zwischen den Aufträgen. Im Autopilot entsteht nur noch ein Szenenbild, ein zweites gibt es auf Knopfdruck.
- **Mein Drehbuch:** Das Studio versteht die üblichen Schreibweisen von ChatGPT, Claude und Gemini, zeigt vor dem Start, was es gelesen hat, und warnt mit Zahlen, wenn eine Folge wenig gesprochen wird. Beschreibungen von Ort und Kleidung laufen unter dem Dialog mit statt als eigene stumme Einstellung. Deine Wörter ändert das Studio nicht.
- **Papierkorb:** eigene Seite mit Bild, Datum, Wiederherstellen und Endgültig löschen. Auf jeder Projektkarte ein Mülleimer (am Handy immer sichtbar), mit Rückgängig.
- **Eigenes Figurenbild** wird jetzt auch nach dem Start übernommen.

## Das neue Studio

- **Neu:** Idee eintippen, Länge, Folgen, Look und Qualität wählen. **Autopilot** an = ohne Zwischenstopps fertig. Oder **Mein Drehbuch**: dein eigenes Drehbuch wortgetreu verfilmen (siehe unten).
- **Projekte:** Alles, was auf dich wartet, steht vorn. Jedes Projekt zeigt genau einen nächsten Schritt und die echte Rechenzeit.
- **Figuren (Reiter):** Deine Figuren-Bibliothek. Bild und Stimme einmal festlegen, in jedem Film wiederverwenden, auch in einem laufenden Projekt (tippe dort auf die Figur).
- **Fertige Filme** liegen im jeweiligen Projekt: ansehen, herunterladen, Beschreibung kopieren. Mit Titelbild gibt es zusätzlich `Cover_<Film>.png`.
- **Lautstärke:** Musik, Geräusche und Umgebung per Regler beim Ton. Bei einem fertigen Film: **Lautstärke und Ton ändern**. Der Autopilot wartet dann auf deine Freigabe.
- **Titelbild:** Beim Anlegen unter „Figuren, Look-Vorlagen, Titelbild und Musik“: am Anfang, nach dem Einstieg oder aus.
- **Aussehen pro Folge:** Bei mehreren Folgen wählst du „Gleich in allen Folgen“ oder „Pro Folge anpassen“. Mit „Pro Folge anpassen“ trägt eine Figur je nach Folge andere Kleidung, etwa in Folge 1 zerrissene Sachen und in Folge 6 einen Anzug. Gesicht und Körper bleiben gleich. Beim Figurencheck steht unter jeder Figur, wie sie in welcher Folge aussieht. Antippen, Wunsch eintippen, **Neu gestalten**: Nur die Szenen dieser Folge mit dieser Figur werden neu gezeichnet.
- **Look-Vorlagen:** Unter „Figuren, Look-Vorlagen und Musik“ bis zu vier Bilder hochladen (JPG, PNG, WebP). Sie bestimmen nur den Stil. Personen daraus kommen nicht in den Film.
- **Figuren:** Jede Figur wird einmal gestaltet und in allen Szenen genau so verwendet. Bekannte Figuren wie SpongeBob werden als Original angelegt. Am sichersten: bei der Figur ein eigenes Bild hochladen.
- **Deine Figuren:** Bei der Bildauswahl siehst du oben jede Figur. **Neu gestalten** zeichnet die Figur und alle Szenen mit ihr neu.
- **Ziel des Films:** Steht über dem Drehbuch: Haken, Wendung, Pointe.
- **Drehbuch:** Die KI schreibt den Film als durchgehendes Gespräch, prüft Wortzahl und Sprecherwechsel und überarbeitet es einmal. Über dem Drehbuch steht eine Prüfzeile: Wörter, Einstellungen, stumme Aktionen, später Sprachanteil und längste Pause.
- **Figuren vorher zeigen:** Ein kurzer Stopp vor den Szenenbildern, auch mit Autopilot. „Neu gestalten“ oder „Eigenes Bild“, dann „Figuren passen, weiter“. Abschaltbar beim Anlegen.
- **Zahnrad oben rechts:** Einrichtung prüfen, **Turbo einrichten**, Stimmen und Animation einrichten, **Benachrichtigungen**, **Unterwegs-Zugriff**, Figurentausch und bisherige Oberfläche.

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

## Unterwegs arbeiten

Du kannst das Studio auch am Handy oder Laptop benutzen, zum Beispiel in der Bahn: Filme anlegen, Bilder, Stimmen, Drehbücher und Musik hochladen, freigeben, Filme ansehen und herunterladen, deine Figuren. Rechnen tut weiter dein PC. Die Verbindung läuft über **Tailscale**, ein kostenloses privates Netz nur aus deinen eigenen Geräten. Öffentlich im Internet ist das Studio dabei nicht.

1. **Am PC:** Tailscale von **tailscale.com/download/windows** laden, installieren und anmelden (zum Beispiel mit deinem Google-Konto).
2. **Am Handy:** die App **Tailscale** installieren (App Store oder Google Play) und mit **demselben Konto** anmelden.
3. **Im Studio am PC:** Zahnrad → **Unterwegs-Zugriff** → **Unterwegs-Zugriff einschalten**. Will Tailscale beim ersten Mal eine Freigabe, zeigt das Studio einen Link: öffnen, bestätigen, dann noch einmal einschalten.
4. **Am Handy:** Tailscale einschalten und die angezeigte Adresse im Browser öffnen. Sie sieht so aus: `https://dein-pc.tailXXXX.ts.net`. Ist Telegram verbunden, schickt dir **Adresse an Telegram senden** den Link aufs Handy.
5. Die Adresse als **Lesezeichen** speichern.

Gut zu wissen:

- Der PC muss an bleiben und das Studio laufen. In den Windows-Energieoptionen **„Energiesparmodus: Nie“** wählen, wenn er am Strom hängt. Sperren (Windows-Taste + L) ist in Ordnung, abmelden oder herunterfahren nicht. Nach einem Neustart einmal **Cay_Studio_Starten.cmd** öffnen.
- Ist der PC aus, ist das Studio nicht erreichbar. Die Tailscale-App zeigt, ob dein PC online ist.
- Aus- und einschalten geht nur am PC selbst. So sperrst du dich unterwegs nicht aus.
- Ist der Unterwegs-Zugriff an, enthalten die Benachrichtigungen den Link **„Im Studio öffnen“**. Er öffnet das Projekt direkt, am Handy (mit Tailscale) und am PC.
- Für die sichere https-Adresse erlaubt Tailscale beim ersten Mal Zertifikate. Dabei kommt der Name deines PCs mit der Adresse (…ts.net) in eine öffentliche Zertifikatsliste. Erreichbar wird das Studio dadurch nicht. Gib dem PC in Tailscale nur keinen Namen, der etwas über dich verrät.

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
