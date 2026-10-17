# Cay Studio 0.18.1 – Unterwegs-Zugriff (17.10.2026)

- **Unterwegs-Zugriff** (Zahnrad → Unterwegs-Zugriff): das Studio am Handy oder Laptop, zum Beispiel in der Bahn. Filme anlegen, hochladen, freigeben, ansehen und herunterladen wie zu Hause, rechnen tut weiter dein PC. Läuft über Tailscale (kostenlos, ein privates Netz nur aus deinen eigenen Geräten, nicht öffentlich im Internet). Ein- und ausschalten nur am PC. Dann enthalten die Benachrichtigungen den Link „Im Studio öffnen“. Schritte: Cay_Studio_Start_und_Update.md → „Unterwegs arbeiten“.
- Kein PC-Neustart nötig. Laufende Projekte laufen einfach weiter.

---

# Cay Studio 0.18.0 – Mein Drehbuch, Figuren-Bibliothek, Titelbild, lebendiger Schnitt, Nachrichten aufs Handy (16.10.2026)

- **Mein Drehbuch:** Beim Anlegen „Die KI schreibt“ oder „Mein Drehbuch“ wählen. Dein fertiges Drehbuch einfügen oder als .md- oder .txt-Datei wählen (PDF geht nicht: dort den Text kopieren oder als .txt speichern). Jeder Satz wird genau so gesprochen, wie er dasteht. Die KI liest das Drehbuch und gestaltet nur Figuren, Bilder und Bewegung dazu, sie ergänzt keine Dialoge und keine Handlung. Beim Tippen prüft das Studio sofort: Figuren, Szenen, Sätze, Wörter, Folgen und „Länge nach Drehbuch“ (mindestens 15 Sekunden, bis 3 Minuten pro Folge), jedes Problem mit Zeilennummer. „Vorlage herunterladen“ zeigt ein Beispiel. Format:
  - `# Titel` ganz oben, für Serien `## Folge 1: Titel`, `## Folge 2: Titel`
  - `FIGUR: Frau Müller – Aussehen und Wesen` (freiwillig, hilft beim Bild)
  - `### Szene 1 – Küche – was man sieht` (oder `Szene 1: Küche`)
  - `OMA (wütend): Text` oder `OMA [wütend]: Text`, ohne Angabe spricht die Figur ruhig. Was im Satz in Klammern steht, wird nicht gesprochen.
  - `AKTION: was ohne Worte passiert` (auch `Aktion:` oder `[Aktion: …]`). Eine Zeile ohne Namen davor zählt auch als Aktion.
- **Figuren-Bibliothek** (Reiter „Figuren“): Bild und Stimme einmal festlegen, in jedem Film wiederverwenden. Auch in einem laufenden Projekt zuweisbar. Rechnet das Studio gerade, wird die Figur vorgemerkt und an der nächsten sicheren Stelle übernommen.
- **Bis zu 30 Figuren** pro Film (vorher 8).
- **Eigenes Bild:** Der Gesichtsausdruck aus dem Bild friert nicht mehr ein. Neu hochgeladene Bilder werden einmal mit neutralem Gesicht nachgezeichnet, jede Szene bestimmt den Ausdruck. Für fertige Figurenblätter: „Bild genau so verwenden“.
- **Titelbild:** am Anfang (Standard), nach dem Einstieg oder aus. Zwei Vorschläge zur Wahl. Zusätzlich liegt `Cover_<Film>.png` neben dem Film.
- **Aussehen pro Folge** (nur bei Serien): beim Anlegen „Gleich in allen Folgen“ (wie bisher) oder „Pro Folge anpassen“. Dann legt die KI für jede Folge fest, wer andere Kleidung trägt oder anders zurechtgemacht ist, zum Beispiel SpongeBob in Folge 1 in zerrissener Kleidung und in Folge 6 im Anzug. Gesicht und Körper bleiben gleich. Für jede Figur und Folge mit neuem Aussehen entsteht ein zusätzliches Figurenbild aus dem Grunddesign. Beim Figurencheck steht es unter der Figur („Folge 3: teurer Anzug“). Antippen, Wunsch eintippen, „Neu gestalten“: Nur die Szenen dieser Folge mit dieser Figur werden neu gezeichnet. Das Titelbild zeigt die Figuren im Grunddesign.
- **Schnitt:** Gespräche in Blöcken statt Ping-Pong, dazu Reaktions-Einstellungen (Zuhörer im Bild, Sprecher aus dem Off) und Orts-Einstellungen. Weniger Lippen-Animation spart Rechenzeit (geschätzt, auf deinem PC noch nicht gemessen).
- **Fertiger Film:** Untertitel in kurzen Wortgruppen, leichte Kamerafahrt, durchgehende Raumatmosphäre, ein „Wusch“ bei stummen Action-Einstellungen.
- **Lautstärke:** Musik, Geräusche und Umgebung per Regler. Bei einem fertigen Film: „Lautstärke und Ton ändern“. Der Autopilot wartet dann, bis du den Ton selbst freigibst. Fertige Animationen werden wiederverwendet.
- **Render-Uhr:** echte Rechenzeit pro Projekt. Restzeit getrennt für Sprech- und Bewegungsabschnitte; vor den ersten fertigen Abschnitten aus früheren Filmen geschätzt.
- **Bild neu machen:** Jede neue Runde sieht anders aus, deine Notiz steht im Bildtext ganz vorn.
- **Benachrichtigungen** (Zahnrad → Benachrichtigungen): Telegram, ntfy oder Browser. Freiwillig und kostenlos. Spricht dich mit „Sir Cay“ an (änderbar), mit Titelbild, wenn der Film fertig ist.
- **Autopilot:** Aus- und wieder Einschalten mitten im Film läuft wieder durchgehend (vorher nur noch schrittweise).
- **Robuster:** Nach einem Absturz oder Neustart rechnet „Fortsetzen“ nur den verlorenen Auftrag neu, statt immer wieder anzuhalten. Turbo an oder aus lässt fertige Sprechabschnitte stehen. Bricht Ollama kurz weg, wartet die Planung und macht allein weiter. Ist die Festplatte kurz voll, läuft die Produktion danach von selbst weiter.
- **Kleinere Verbesserungen:** Projekte in den Papierkorb legen (Wiederherstellen möglich). „Neue Fassung planen“ fragt, was anders werden soll. Entfernte Figur mit „Rückgängig“. Eigene Musik wieder entfernen. Eingabefehler auf Deutsch. Uploads auch per Tastatur. Nach „Lautstärke und Ton ändern“ holt „Abbrechen, fertigen Film behalten“ den alten Film zurück.
- **Deine Meldungen aus 0.17:** Eine Figur mit mehreren Schreibweisen („Mr Krabs“, „Mr. Krabs“, „Krabs“, „Larry der Hummer“) zählt jetzt als eine Figur. Ist ein KI-Text zu lang, wird er am Satzende gekürzt, statt die Planung abzubrechen. Plant die KI eine andere Zahl an Folgen als gewählt, hält das Studio vor dem ersten Bild mit einer Meldung an.
- **Endgültig löschen:** Im Papierkorb gibt es „Endgültig löschen“. Die fertigen Videos werden nur gelöscht, wenn du die zweite Frage bestätigst. Bibliothek und Uploads bleiben.
- Ein älteres Update-Programm wird nicht mehr über 0.18 installiert.
- Laufende Projekte behalten Schnitt, Stimmen und Bildtexte von 0.17. Die Neuerungen gibt es für neue Filme und mit „Neue Fassung“. Kein PC-Neustart nötig.

---

# Cay Studio 0.17.0 – Drehbuch als Gespräch, feste Figuren, kürzere Rechenzeit (14.10.2026)

- Drehbuch: Die KI schreibt den ganzen Film zuerst als durchgehendes Gespräch (mit Denkmodus), prüft Wortzahl, Sprecherwechsel und Telegrammstil, überarbeitet ihn einmal als „Script Doctor“ und schneidet erst dann in Einstellungen.
- Keine langen Pausen mehr in Sprechszenen: nach dem letzten Wort höchstens etwa eine halbe Sekunde. Fehlende Zeit wird zu stummen Aktionsszenen.
- Bildtexte nennen nur Figuren, die im Bild sind. Bekannte Figuren (z. B. SpongeBob) bekommen keine Stilübertragung von Vorlagen.
- „Figuren vorher zeigen“: ein kurzer Stopp vor den Szenenbildern, auch mit Autopilot. Dort: neu gestalten oder eigenes Bild.
- Stimmen: Gefühls-Sprechproben mit passendem Text, 16 Sprechhaltungen, bei Knete/Cartoon eine Cartoon-Sprechweise, bei Gefühlszeilen zwei Aufnahmen und die lebendigere gewinnt.
- Schneller: Die Lippen-Animation rechnet nur noch im ersten von vier Schritten doppelt (vorher in allen vier).
- Nach dem Update einmal den PC neu starten: Erst dann lädt ComfyUI die schnellere Lippen-Animation. Ohne Neustart hält ein neuer Film mit genau diesem Hinweis an.
- Projekte, die schon in 0.16 Stimmen oder Animation hatten, behalten Stimmen, Szenenlängen und Bewegungstexte. So wird nichts doppelt gerechnet. Die Neuerungen gibt es für neue Filme und mit „Neue Fassung“.

---

# Cay Studio 0.16.1 – Tonmischung repariert (14.10.2026)

- Behebt „Tonmischung unvollständig; keine Freigabe“. Ursache: Der Lautheitsfilter von FFmpeg verschiebt die Zeitstempel; bei Filmlängen wie 60,12 s fehlte danach das Ende.
- Im angehaltenen Projekt einfach „Fortsetzen“. Bilder und Stimmen bleiben erhalten.

---

# Cay Studio 0.16.0 – feste Figuren, mehr Tempo, Ziel des Films (14.10.2026)

- Look-Vorlagen bestimmen nur noch den Stil. Personen aus der Vorlage kommen nicht mehr in den Film.
- Jede Figur wird einmal gestaltet und in allen Szenen genau so verwendet. Bekannte Figuren (z. B. SpongeBob) werden als Original angelegt.
- Bei der Bildauswahl: „Deine Figuren“ mit „Neu gestalten“. Alle Szenen mit dieser Figur werden dann neu gezeichnet.
- Vor dem Drehbuch legt die KI das Ziel des Films fest: Haken, Steigerungen, Wendung, Pointe.
- Mehr Bewegung: lebendige Gesten, kurze Sätze, Sprache beginnt direkt am Schnitt.
- Sprechszenen werden vor Bewegungsszenen gerechnet: weniger Neuladen der großen Modelle.

---

# Cay Studio 0.15.0 – Turbo, Look-Vorlagen, Warteschlange (14.10.2026)

- Turbo für Sprechszenen (Zahnrad oben rechts), nur nach bestandener Probe, schaltet sich bei Fehlern selbst ab.
- Look-Vorlagen: bis zu vier Bilder (JPG, PNG, WebP). Neuer Look „Knete“.
- Oberfläche nur noch „Neu“ und „Projekte“; Projekte zeigen ihren Platz in der Warteschlange.
- Diagnose zeigt, wie Grafikkarte, Prozessor, Arbeitsspeicher und SSD zusammenarbeiten.

Plan und Grenzen: CAY_STUDIO_PLAN.md im Update-Ordner.

---

# Cay Studio 0.14.0 – neues Studio, Autopilot, Serien (13.10.2026)

- Neue Oberfläche unter http://127.0.0.1:8787 (bisherige unter /classic, dort auch der Figurentausch).
- Autopilot: Filme ohne Zwischenstopps fertigstellen.
- Serien bis 12 Folgen mit offenem Ende und „Teil X/Y“ im Bild, Beschreibung mit Hashtags pro Folge.
- Qualität „Entwurf“ (schneller) und „Standard“. 25 Bilder pro Sekunde, Sprechszenen ohne Umrechnung.
- Ton auf −14 LUFS für Handy und TikTok.

Plan, Messwerte und Grenzen: CAY_STUDIO_PLAN.md im Update-Ordner.

---

# Cay Studio 0.13.4 – Zeitmessung inklusive Stimmen (13.10.2026)

- Die Spracherzeugung wird jetzt wie Planung, Bilder und Animation gemessen.
- Cay_Studio_Diagnose.cmd zeigt eine Zeittabelle pro Projekt.

---

# Cay Studio 0.13.3 – hängende Abschnitte lösen, „Schnell“ als Standard (12.10.2026)

- Hängt ein Abschnitt länger als 10 Minuten ohne neuen Rechenschritt, erscheint eine Karte mit **„Abbrechen · mit „Schnell“ weiter“**.
- Nach einem PC-Neustart bleibt ein Projekt nicht mehr dauerhaft bei „Status erneut prüfen“ hängen: **„Abschnitt neu starten“**.
- Neue Projekte starten mit **„Schnell“** (4 statt 40 Rechenschritte). „Hohe Qualität“ bleibt wählbar.
- Diagnose zeigt zusätzlich Schnell-Gewichte, Grafikspeicher und die letzten ComfyUI-Meldungen.

---

# Cay Studio 0.13.2 – kein stummer Film mehr durch leeres Drehbuch (11.10.2026)

- Sprechen zwei sichtbare Figuren in einer Szene, teilt das Studio sie jetzt in **Schuss und Gegenschuss** auf. Bisher wurden solche Dialoge verworfen, und der Film blieb stumm.
- Hat ein Drehbuch **kein einziges gesprochenes Wort**, obwohl Figuren sprechen sollen, hält das Studio **vor den Bildern** an. „Folge neu planen“ startet die Planung neu.
- Ältere Projekte ohne Dialog halten vor der Tonmischung an. Dort „Neue Fassung planen“ wählen.
- Neu im Update-Ordner: **Cay_Studio_Diagnose.cmd**. Liest nur und schreibt **Cay_Studio_Diagnose.txt**.

---

# Cay Studio 0.13.1 – Sprachprüfung pro Dialogbeitrag (09.10.2026)

Kein PC-Neustart nötig. Update installieren, **Cay_Studio_Starten.cmd** öffnen, im Browser **Strg+F5**. Unten muss **0.13.1** stehen.

- Jede Tonvorschau prüft jetzt **jeden einzelnen Dialogbeitrag**. Ist einer stumm oder von Musik verdeckt, hält das Studio an und nennt **Folge, Szene, Figur und Text**.
- **Produktion fortsetzen** spricht dann **nur diese Beiträge** neu ein. Alle anderen Stimmen bleiben unverändert.
- Der fertige Film wird mit der freigegebenen Tonvorschau verglichen. Fehlt dort Sprache, wird er nicht als fertig gespeichert.
- Kurze Ausrufe wie „Nein!“ werden nicht mehr akzeptiert, wenn die Aufnahme nur ein Klick oder Atmer ist.

Geprüft mit echter FFmpeg-Mischung und künstlichen Testsignalen, nicht mit echten KI-Stimmen auf deiner RTX 4090.

---

# Cay Studio 0.13.0 – Reparaturupdate vom 29.09.2026

Nach erfolgreichem Update den PC einmal neu starten, dann **Cay_Studio_Starten.cmd** öffnen und im Browser **Strg+F5** drücken. Der Neustart lädt den neuen ComfyUI-Samplerknoten; keine neuen Modellgewichte erforderlich. Laufende Produktionen vorher nach ihrem aktuellen Schritt pausieren.

- Renderfehler: Projekt öffnen → **Produktion fortsetzen**. Die Ursache und ein Diagnose-Download sind direkt sichtbar.
- Lange Sprechpausen: **Dialoge & Ton bearbeiten** → **Dialoge ergänzen**. Neue Mischung anhören, erneut freigeben und Produktionsprobe prüfen.
- Projekte lassen sich nach einem Fehler wieder öffnen. Löschen blendet sie aus; der Papierkorb erhält Dateien und pausiert die Arbeit.
- GPU, WSL-CPU und freier RAM in Windows/WSL erscheinen während der Produktion. Beide Prozessoren müssen nicht gleichzeitig 100 % anzeigen.

Der Sampleradapter begrenzt die Behandlung von fehlenden Zahlenwerten auf dokumentierte deaktivierte Optionen. Fremde ComfyUI-Dateien werden nicht verändert. Die tatsächliche GPU-Inferenz und Laufzeit müssen auf dem Ziel-PC geprüft werden; aus einer Fehlermeldung ohne Stacktrace lässt sich nicht jede Ursache bestimmen.

---

## Bisherige Dokumentation

# Cay Studio 0.12.0 – einfache Anleitung

Stand: 29.09.2026. Du hast bereits 0.11.0. Du brauchst keine komplette Neuinstallation.

## Jetzt das Update installieren

1. **Cay_Studio_Updatepaket_0.12.0.zip** herunterladen. Rechtsklick darauf → **Alle extrahieren**.
2. Falls gerade ein Video oder eine Einrichtung läuft: erst den laufenden Schritt beenden lassen; Produktionen danach pausieren.
3. Im entpackten Ordner **Cay_Studio_Update.cmd** doppelklicken. Alle Dateien müssen zusammenbleiben.
4. Auf die Erfolgsmeldung warten. Im Browser **Strg + F5** drücken. Unten muss **0.12.0** stehen.
5. Dein Projekt **„Butterblitzs Fehlkalkulation“** öffnen und **Planung fortsetzen** anklicken.

Meldet das Update „beschäftigt“: den laufenden Schritt abwarten und dieselbe Update-Datei erneut starten. Nichts löschen. Der Installer sichert die Datenbank; Projekte, Bilder, Stimmen und fertige Filme bleiben erhalten.

## Danach den Figurentausch benutzen

1. **Figurentausch** öffnen und einmal **Figurenstudio ergänzen** anklicken, falls angeboten. Für deine bestehende Einrichtung kommt ein Prüfmodell von etwa **0,8 GB** hinzu; mindestens **3 GB frei** halten. Die Anzeige meldet, wenn alles bereit ist.
2. Das **Originalvideo** und dein Hundebild hochladen. Typ **Hund** wählen. Für die erste Probe einen Ausschnitt von **2–3 Sekunden** nehmen. Nicht den bereits fehlerhaft erzeugten Hund/Mensch-Clip als Original benutzen.
3. **Punkt 1** auf die Figur im Original setzen. Bei mehreren Figuren: **Weitere Figur**, zweites Bild, **Punkt 2** auf die zweite Figur. Jeder Punkt gehört zu seinem eigenen Bild; höchstens vier Figuren.
4. Vorbereitung starten. Die Bilderreihe zeigt die Ersatzfigur jetzt **am Anfang, unterwegs und am Schluss**. Alle Bilder prüfen. Dann **Figurenbilder passen · Animieren** anklicken. Stimmt schon ein Bild nicht: **Auswahl ändern**.
5. Das fertige Vorschauvideo vollständig ansehen. Erst wenn es passt: **Video passt · Als fertig speichern**. Dann landet es bei den fertigen Videos.

Findet die automatische Prüfung einen möglichen Figurenwechsel, versucht das Studio den betroffenen kurzen Abschnitt einmal erneut. Bleibt er auffällig, hält es an und zeigt die betreffende Stelle. Du kannst **Diesen Abschnitt neu versuchen** oder **Figur oder Auswahl ändern** wählen. Die automatische Prüfung kann sich irren; sie ersetzt deine Sichtprüfung nicht.

Alte fertige Videos werden nicht verändert. Für das misslungene Video eine neue Bearbeitung aus dem Original anlegen. Noch nicht fertige alte Aufträge bekommen bei der Fortsetzung die neuen Figurenbilder und benötigen eine erneute Freigabe. Bei einer vollständigen Figurentausch-Ersteinrichtung sind mindestens 32 GB freier Speicher und größere Modelldownloads nötig.

## Nach einem PC-Neustart öffnen

**Cay_Studio_Starten.cmd** im entpackten Ordner doppelklicken. Falls sich kein Browser öffnet: **http://127.0.0.1:8787** aufrufen; alternativ **http://localhost:8787**.

Diese Startdatei kannst du immer wieder verwenden. Die enthaltene Starthilfe 1.1 behebt den früheren Fehler `wslpath: D:Cay_Studio...`; auch Ordner mit Leerzeichen sind zulässig. Nicht direkt aus dem ZIP starten. Die Update-Datei brauchst du nur zum Aktualisieren.

## Was sich verbessert hat

| Bereich | Änderung in 0.12.0 |
| --- | --- |
| Deine Fehlermeldung | Fehlende Angaben zum Szenenaufbau werden gezielt ergänzt. Dramaturgische Hinweise allein blockieren die Planung nicht mehr; technische Fehler bleiben sichtbar. |
| Figurenverlauf | Regelmäßige Ersatzbilder führen die Animation durch den gesamten Ausschnitt. Kurze Abschnitte und eine lokale Bildprüfung helfen, Rückwechsel früh zu erkennen. |
| Ergebnisfreigabe | Jeder neue Figurentausch bleibt zuerst eine Vorschau. Erst deine Freigabe speichert ihn als fertiges Video. |
| Einrichtung | Automatisch aktualisierter Status mit einem klaren nächsten Schritt. Technische Details sind aufklappbar. |
| Bearbeitung | Bilder, Ton, ungespeicherte Eingaben und Scrollposition bleiben bei Statusänderungen erhalten. Die Prüfung mit 40 Bildern ist bestanden. |

Die neue Bildprüfung hat den Hund-zu-Mensch-Wechsel in deinem eingesandten Video ab etwa **1,75 Sekunden** erkannt. Das ist ein echter Test mit dem Prüfmodell. Eine neue Animation auf deiner RTX 4090 ist damit noch nicht geprüft. Die zusätzlichen Figurenbilder benötigen Rechenzeit; die frühe Prüfung und die begrenzten Wiederholungen sollen lange unbrauchbare Renderläufe vermeiden. Eine feste Renderzeit lässt sich hier nicht seriös nennen.

## Nur falls Animation oder Stimmen noch fehlen

Bereits eingerichtete Komponenten musst du nicht erneut installieren.

1. **Neues Video → Einrichtung prüfen** öffnen. Falls etwas fehlt, **Fehlende Komponenten einrichten** wählen. Für die vollständige Animationsersteinrichtung mindestens **60 GB frei** halten.
2. Wenn ein Neustart verlangt wird: laufende Produktionen pausieren und ihren aktuellen Schritt abwarten, dann PC neu starten und **Cay_Studio_Starten.cmd** öffnen.
3. Für die erste Probe **Schnell · 4 Schritte, Zusatzgewichte** und bei Dialogen **Mit Ton gesteuerte Mundbewegungen** wählen.
4. Steht bei den Stimmen **Qwen-Dialoge bereit**, ist die Einrichtung vorhanden. Eine **neue Tonvorschau** erzeugen und anhören. Alte Tondateien werden nicht automatisch neu gesprochen.
5. Erst Bilder und Ton freigeben, danach die kurze **Produktionsprobe** ansehen. Mit **Passt · Produktion fortsetzen** startet die weitere Produktion.

Für neue Filmpläne gilt: **60 Sekunden = 10 Szenen je Folge**, **90 Sekunden = 15**, unabhängig von der Zahl der bestellten Folgen. Bereits gespeicherte Geschichten werden nicht allein durch das Update umgeschrieben. Bei sprechenden Figuren nutzt die neue Planung einen sichtbaren Sprecher je Einstellung; ältere Mehrfiguren-Sprechszenen brauchen gegebenenfalls eine neue Fassung oder bewusst **Nur Bildbewegung / Off-Kommentar**.

Alle Modelle laufen lokal. Es werden keine Abo-Dienste, kostenpflichtigen APIs oder Testguthaben eingerichtet. Internet wird für die einmaligen öffentlichen Modelldownloads benötigt; der PC verbraucht weiterhin Strom. Es wurde kein externer Renderdienst aktiviert.

## Falls noch etwas nicht startet

Beim Öffnen: **Cay_Studio_Startprotokoll.txt** aus dem entpackten Ordner schicken. Bei einem Projektfehler: **Diagnose herunterladen** benutzen. Projekte, Modelle oder Datenbank nicht auf Verdacht löschen.

Falls die Startdatei nicht hilft, ist dies der Ersatzbefehl für **Windows PowerShell**:

```powershell
wsl.exe -d Ubuntu -u alihu --exec /home/alihu/ki-video/studio/venv/bin/python /home/alihu/ki-video/studio/current/launcher.py --open-browser
```

Danach http://127.0.0.1:8787 öffnen. ComfyUI, Ollama und Dashboard sind getrennte Dienste; laufendes ComfyUI allein öffnet das Studio nicht.

Geprüft: lokaler Webserver, Datenbank, FFmpeg-Ausgaben mit Ton, Freigaben und Wiederaufnahme, Desktop/Handy, Update mit Datensicherung und Rückkehr bei Startfehler. In diesen Ablaufprüfungen waren die generierenden KI-Modelle simuliert; die zusätzliche Bildprüfung wurde wirklich auf deinem Video ausgeführt. Neue GPU-Bildqualität, Stimmklang, Lippensynchronität und Geschwindigkeit bleiben auf deinem PC zu prüfen. Absolute Fehlerfreiheit kann das Update nicht garantieren.
