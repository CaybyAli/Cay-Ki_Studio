# Cay Studio 0.13.0 – so geht es weiter

## Einmal das Update installieren

1. **Cay_Studio_Updatepaket_0.13.0.zip** herunterladen. Rechtsklick → **Alle extrahieren**.
2. Wenn noch eine Produktion läuft: **Pausieren** anklicken und den aktuellen Abschnitt beenden lassen. Eine laufende Einrichtung fertig werden lassen. Bereits angehaltene Fehlerprojekte können so bleiben.
3. Im entpackten Ordner **Cay_Studio_Update.cmd** doppelklicken. Alle enthaltenen Dateien müssen zusammenbleiben.
4. Warten, bis **CAY STUDIO 0.13.0 INSTALLIERT** erscheint. Dann **den PC einmal neu starten**. Dadurch lädt ComfyUI die Sampler-Reparatur.
5. Im gleichen Ordner **Cay_Studio_Starten.cmd** doppelklicken. Im Browser **Strg + F5** drücken. Unten muss **0.13.0** stehen.
6. **Meine Projekte → dein Projekt → Produktion fortsetzen**.

Meldet das Update „beschäftigt“: den laufenden Schritt abwarten und dieselbe Update-Datei erneut starten. Nichts löschen und keine Grundinstallation starten. Der Installer sichert die Datenbank. Projekte, Bilder, Stimmen und fertige Abschnitte bleiben erhalten.

## Wenn die Dialoge zu kurz sind

1. Im angehaltenen Renderprojekt auf **Dialoge & Ton bearbeiten** klicken. Bist du bereits bei der Tonvorschau, dort bleiben.
2. Gewünschte **Folge** auswählen und **Dialoge ergänzen** anklicken.
3. Der Änderungswunsch ist schon eingetragen. Auf **Änderung anfordern** klicken. Ist das Projekt pausiert, Fenster schließen und **Fortsetzen** wählen.
4. Warten, bis die neue Tonvorschau bereit ist. Anhören und die Anzeige **Sprache / Sprechpausen / längste Pause** prüfen.
5. Erst danach erneut **produzieren** und die kurze **Produktionsprobe freigeben**.

Vorhandene Texte und Szenenbilder bleiben erhalten. Die KI ergänzt passende Reaktionen, Widerspruch oder Entscheidungen. Nur die ausgewählte Folge erhält zusätzliche Dialoge; bei mehreren Folgen nach Bedarf wiederholen. Neue Sprache kann eine Neuberechnung betroffener Animationen nötig machen. Wenn die KI keine gültige Ergänzung liefert, erscheint ein Hinweis und die vorhandene Vorschau bleibt erhalten. Ein bewusst stummer Film wird bei der neuen Planung berücksichtigt.

## Cay Studio nach einem Neustart öffnen

Immer **Cay_Studio_Starten.cmd** doppelklicken. Die Update-Datei brauchst du nur für eine Aktualisierung.

Öffnet sich kein Browser: **http://127.0.0.1:8787** eingeben. Alternativ **http://localhost:8787**.

Der Starter enthält die Pfadkorrektur für den früheren Fehler `wslpath: D:Cay_Studio...`. Nicht direkt aus dem ZIP starten.

## Was repariert wurde

- **Projekt öffnen:** Der konkrete Oberflächenfehler `root.insertAdjacentHTML is not a function` ist behoben. Auch angehaltene und fertige Projekte können angezeigt werden.
- **Papierkorb:** Gelöschte Projekte verschwinden aus der Übersicht. Verspätete Antworten können sie nicht wieder einblenden. Wiederhergestellte Projekte erscheinen sofort und bleiben zunächst pausiert. Die Projektdateien bleiben im Papierkorb absichtlich erhalten und belegen Speicher.
- **Renderfehler:** Statt einer unklaren „Prüfung nötig“-Anzeige stehen Ursache und nächste Aktion direkt im Projekt.
- **Sampler:** Fehlende numerische Standardwerte werden explizit gesetzt. Ein separater ComfyUI-Knoten fängt die bekannte Variante des `NoneType`-Vergleichs bei deaktivierten Zähleroptionen ab. Fremde Erweiterungsdateien bleiben unverändert.
- **Dialoge:** Neue Pläne bekommen eine zusätzliche Dialogprüfung. Vorhandene Folgen lassen sich gezielt ergänzen. Die Zeitplanung verteilt freie Zeit stärker auf sprechende Einstellungen.
- **Speicher:** Zwischen verschiedenen Modellarten und an Wartepunkten wird die Freigabe ungenutzter ComfyUI-Caches angefordert, sofern dessen Warteschlange leer ist. Die Produktionsansicht zeigt GPU-Auslastung und freien RAM in Windows und WSL samt Engpasshinweisen.
- **Bearbeitung:** Statusänderungen erhalten unveränderte Bilder, Audioelemente, Eingaben und Scrollposition. Mit 40 Bildern geprüft.

## Zu deiner CPU-, GPU- und RAM-Anzeige

**CPU und GPU müssen nicht beide bei 100 % liegen.** Modellladen, Speicherübertragungen, KI-Berechnung und Videoschnitt beanspruchen unterschiedliche Komponenten. Die Gesamtauslastung eines Prozessors mit vielen Kernen kann niedrig aussehen, obwohl einzelne Kerne arbeiten. Im Windows-Task-Manager sind 3D- und Videodecoder-Diagramme zudem andere Messungen als die KI-Berechnung.

Auf deinem Screenshot sind nur etwa **2,7 GB von rund 64 GB RAM frei**. Das ist ein möglicher Engpass; aktive Auslagerung kann die GPU ausbremsen. Nicht benötigte Programme schließen und keine zweite Produktion starten. Die neue Anzeige zeigt Warnungen bei knappem RAM sowie aktive Auslagerung unter „Leistung & Laufzeiten“. Sie misst, ob der Verdacht zutrifft; das Foto allein beweist die Ursache nicht. Das Update ändert keine Windows- oder WSL-Speichergrenzen.

## Figurentausch und kurze Produktionsprobe

Die Verbesserungen aus 0.12 bleiben enthalten: mehrere nummerierte Figuren mit eigenen Bildern, Ersatzbilder über den Verlauf, Prüfung auf mögliche Rückwechsel und eine abschließende Videofreigabe. Für ein misslungenes Hund/Mensch-Video eine neue Bearbeitung aus dem **Originalvideo** anlegen, Typ **Hund** wählen und zunächst einen **2–3-Sekunden-Ausschnitt** vollständig prüfen. Bereits fertige Videos werden durch das Update nicht nachträglich verändert.

Für einen neuen KI-Film zuerst **Schnell** und bei Dialogen **Mit Ton gesteuerte Mundbewegungen** wählen. Die kurze Produktionsprobe vor der ganzen Serie ansehen. Die Darstellung einer Figur und perfekte Lippensynchronität lassen sich nicht allein durch einen bestandenen Softwaretest garantieren.

## Falls derselbe Renderfehler wiederkommt

Im Projekt auf **Fehlerbericht speichern** klicken und die Datei hier schicken. Der Bericht enthält den vollständigen Fehlerpfad; die kurze `NoneType`-Meldung allein kann mehrere Ursachen haben. Beim Startproblem stattdessen **Cay_Studio_Startprotokoll.txt** aus dem entpackten Ordner schicken. Keine Modelle oder Projekte auf Verdacht löschen.

Nur falls die Startdatei nicht funktioniert: **Windows PowerShell** öffnen und diese eine Zeile eingeben:

```powershell
wsl.exe -d Ubuntu -u alihu --exec /home/alihu/ki-video/studio/venv/bin/python /home/alihu/ki-video/studio/current/launcher.py --open-browser
```

## Prüfstand

Browserprüfung mit Projektfehler, Papierkorb, 40 Bildern, Tonkorrektur und schmalem Bildschirm; echte FastAPI-/SQLite-Prüfung der Projektzustände; gezielte Sampler-, Dialog- und Medientests; Update von 0.12 auf 0.13 mit Sicherung und Rückkehr zur vorherigen Version bei einem absichtlich fehlerhaften Start.

**Das Update ist bereitgestellt, aber noch nicht auf deinem PC installiert.** Eine neue GPU-Produktion, der Stimmklang und die tatsächliche Renderzeit auf deiner RTX 4090 sind hier nicht geprüft. Eine fehlerfreie KI-Ausgabe oder feste Zeitersparnis wäre daher kein ehrliches Versprechen.

Alles bleibt lokal. Dieses Update richtet keine Abos, kostenpflichtigen APIs oder externen Renderdienste ein und benötigt keine neuen Modellgewichte. Stromverbrauch und gegebenenfalls schon zuvor erforderliche Modellinstallationen bleiben davon unberührt.
