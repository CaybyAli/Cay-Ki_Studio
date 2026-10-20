# Cay Studio – Plan (Stand 0.18.0, 16.10.2026)

Ziel: mehrere 1-Minuten-Videos pro Tag, Einzelfilme und Serien bis 12 Folgen, lokal und ohne laufende Kosten.

**[Sicher]** = gemessen oder getestet · **[Hochrechnung]** = aus deinen Messwerten gerechnet · **[Vermutung]** = noch nicht belegt.

## 1. Wo die Zeit hingeht

| Arbeitsschritt | Zeit beim 15-s-Keks-Film | Wer arbeitet |
| --- | --- | --- |
| Drehbuch | 2,7 min | Grafikkarte (Sprachmodell) |
| Bilder | 0,6 min | Grafikkarte |
| Animation | **82,7 min (95 %)** | Grafikkarte |
| Schnitt, Ton, Export | 1,4 min | Prozessor, parallel |

**[Sicher]** Die Animation entscheidet alles. Im ComfyUI-Protokoll braucht der schnellste 5-s-Abschnitt 9 min, der Durchschnitt liegt bei 20,7 min. Diese Lücke ist verschenkte Zeit.

## 2. Dein PC als Team

| Teil | Aufgabe im Studio | Was zählt |
| --- | --- | --- |
| **RTX 4090** | Rechnet Drehbuch, Bilder, Stimmen und Animation | Nie warten, nie auslagern. Turbo nutzen. |
| **Ryzen 9 7950X3D** | Schnitt, Untertitel, Tonmischung, Sprachprüfung, Export, alles parallel zur Grafikkarte | Hält der Grafikkarte den Rücken frei. Die KI-Rechnung selbst wäre auf dem Prozessor etwa 50-mal langsamer und hilft deshalb nicht. |
| **64 GB RAM** | Hält die großen Modelle bereit, damit die Grafikkarte nicht auf die SSD wartet | Richtig zwischen Windows und WSL aufgeteilt. Wird es knapp, lädt ComfyUI Modelle neu: **[Vermutung]** Ursache für 9 statt 20,7 min. |
| **SSD** | Lädt Modelle | Modelle im WSL-Laufwerk (schnell), nicht über das Windows-Laufwerk D: |
| **X670E Taichi** | Verbindet Grafikkarte und Speicher | Grafikkarte im obersten Steckplatz mit voller Breite (x16). Die Diagnose prüft das. |

Teamwork heißt hier also: **Die Grafikkarte rechnet ohne Pause, alles andere arbeitet ihr parallel zu.** Ein „alle Teile auf 100 %“ gibt es bei dieser Arbeit nicht.

## 3. Was 0.15.0 dafür tut

1. **Turbo** (SageAttention): eine schnellere Rechenart für Sprechszenen, kostenlos. Erwartet 1,5- bis 2-fach **[Vermutung]**. Wird nur benutzt, wenn eine echte Probe auf deiner Grafikkarte bestanden ist. Schlägt ein Abschnitt fehl, schaltet sich Turbo selbst ab.
2. **Warteschlange und Autopilot:** Mehrere Ideen nacheinander eintragen. Das Studio arbeitet sie der Reihe nach ab, auch nachts. Die Projektliste zeigt, wer gerade dran ist.
3. **Diagnose „PC als Team“:** RAM, Auslagerung, WSL-Einstellung, PCIe, Speicherort der Modelle, Lade- und Rechenzeiten aus ComfyUI.
4. **Look-Vorlagen** (bis 4 Bilder, auch JPG/WebP) und **Look „Knete“** für Clay-Serien.
5. Oberfläche: nur noch **Neu** und **Projekte**, keine überlappenden Knöpfe.

## 3b. Was 0.16.0 nach deinem SpongeBob-Test ändert

| Dein Problem | Ursache im Code | Änderung |
| --- | --- | --- |
| Personen aus der Vorlage im Film | **[Sicher]** Vorlagen gingen als Bildvorgabe in die Figurengestaltung und füllten in jeder Szene die freien Plätze auf | Figur zuerst nur aus Text, danach nur Stil aus der Vorlage. Szenen bekommen nur noch die Figurenbilder. |
| SpongeBob ändert 3–4 Mal das Gesicht | **[Wahrscheinlich]** Vorlagen-Personen vermischten sich pro Szene anders mit der Figur. **[Sicher]** Eine Bildkorrektur an einer Figur zeichnete nur eine Szene neu, die anderen behielten das alte Gesicht. | Ein festes Figurenbild für alle Szenen; jede Änderung an einer Figur zeichnet alle ihre Szenen neu; „Neu gestalten“ bei der Bildauswahl. |
| Ähnliche Figur statt SpongeBob | **[Sicher]** Der Auftrag lautete „One original character design“, also ausdrücklich eine neue Figur | Bekannte Figuren werden als Original angelegt („not a look-alike“). |
| Keiner bewegt sich, Zeitlupe | **[Sicher]** Vorgabe „zurückhaltende Gesten“, Zuhörer still; Sprache startete erst nach einer Pause mitten in der Einstellung. **[Wahrscheinlich]** Die schnellen 4-Schritt-Modelle bewegen ohnehin wenig. | Lebendige Gesten, Bewegung „nie Zeitlupe“, leichte Kamerafahrt, Sprache direkt am Schnitt, Restzeit wird Handlung statt Pause, kurze Sätze. |
| Planung ohne Gesamtziel | **[Sicher]** Szenen, Prüfung und Dialogergänzung wurden ohne gemeinsames Ziel geplant | Zuerst „Ziel des Films“ (Haken, 2–3 Steigerungen, Wendung, Pointe). Jeder weitere Planungsschritt bekommt es. |
| 5 Stunden | **[Sicher]** Beim Wechsel Sprechszene ↔ Bewegungsszene wurden alle Modelle entladen | Erst alle Sprechszenen, dann alle Bewegungsszenen. Wie viel das spart, hängt von deinem Film ab **[Vermutung]**. |

**Grenzen, ehrlich:**
1. Ob das Bildmodell SpongeBob ohne Bild exakt trifft, ist nicht geprüft **[Vermutung]**. Sicher ist nur: Mit deinem eigenen Bild der Figur gibt es die feste Vorlage.
2. Mehr Bewegung kann mehr Fehler an Armen und Händen bringen. Bitte darauf achten.
3. 0.16 löst die 5 Stunden nicht. Dafür brauche ich deine neue Diagnose: Sie zeigt jetzt Rechenfenster, Minuten pro Fenster und Modellwechsel.

## 3c. Was 0.17.0 nach dem Krusty-Film ändert

Grundlage: dein Video (Einzelbilder und Tonpausen gemessen), Diagnose 0.16.1, fünf Code-Prüfungen, zwei Recherchen, Quelltext der Animations-Erweiterung (Stand 088128b).

| Dein Problem | Ursache | Änderung |
| --- | --- | --- |
| Mund und Hände bewegen sich ohne Text | **[Sicher]** Nur 25 von 60 s waren Sprache. Die fehlenden 35 s hängte 0.16 als Stille ans Ende jeder Sprechszene (2,2 bis 4,5 s). Dazu verlangte der Text „Bewegung die ganze Zeit“. | Sprechszene endet höchstens ~0,6 s nach dem letzten Wort. Fehlende Zeit wird zu stummen Aktionsszenen. Vorgabe: Gesten nur beim Sprechen, in Pausen Mund zu. |
| Text langweilig, teils sinnlos | **[Sicher]** Das Wortziel wurde nie durchgesetzt (63 statt ~120 Wörter). Fester Rahmen von 10 Szenen mit je einem Sprecher. Fünfmal „kurz / höchstens acht Wörter“. Dialog war ein Feld unter sechzehn, ohne Nachdenken geschrieben. | Drehbuch zuerst als ganzes Gespräch mit Denkmodus. Geprüft: Wortzahl, Sprecherwechsel, Telegrammstil, Besetzung. Fehler gehen mit Zahlen zurück an die KI. Danach Script Doctor, erst dann Schnitt. |
| Fremde Figuren im Bild | **[Sicher]** Der Bildtext enthielt die ganze Szenenhandlung mit allen Namen. Das Bildmodell malt jede genannte Figur, ohne Vorlage, also falsch oder vermischt. | Bildtext nennt nur Figuren im Bild. Sätze über andere Figuren werden gestrichen. |
| Mr. Krabs als Wurst, Plankton als grüner SpongeBob | **[Sicher]** „… from the animated series SpongeBob SquarePants“ stand in jedem Figurenentwurf und Szenenbild. **[Wahrscheinlich]** Die Stilübertragung mit Vorlagen gab Mr. Krabs einen Menschenkörper. | Figuren nur mit eigenem Namen. Keine Stilübertragung bei bekannten Figuren. Körperbau zuerst. „Figuren vorher zeigen“ mit „Neu gestalten“ und „Eigenes Bild“. |
| Monotone Stimmen | **[Sicher]** Die Gefühls-Sprechproben sprachen alle denselben ruhigen Erzähltext. 29 von 40 Gefühlswörtern landeten bei „neutral“. Die Tonmischung glättete laut und leise. | Pro Gefühl ein passender Probetext, 16 Sprechhaltungen, Cartoon-Sprechweise bei Knete/Cartoon, zwei Aufnahmen pro Gefühlszeile (die lebendigere zählt), Schreien lauter und Flüstern leiser in der Mischung. |
| ~2 h pro Film | **[Sicher]** Mit Audio-Führung 2.0 rechnet die Lippen-Animation jeden der 4 Schritte doppelt (8 Durchläufe pro Rechenblock). | Audio-Führung nur im ersten Schritt: 5 statt 8 Durchläufe. **[Hochrechnung]** Rechenblock ~3,4 → ~2,3 min. Dazu: kein Rechenblock mehr für bloße Stille, knapp zu lange Szenen werden eingepasst. |

**Ehrliche Grenzen:**
1. Nichts davon ist auf deiner Grafikkarte getestet. Ob Lippen mit Audio-Führung nur im ersten Schritt genauso gut sitzen, zeigt erst dein Film **[Vermutung: kaum Unterschied]**.
2. Ob das 4B-Bildmodell Mr. Krabs und Plankton ohne Bild trifft, bleibt offen. Mit deinem eigenen Bild ist es sicher.
3. Die Drehbuchqualität hängt am lokalen Planungsmodell. Der Denkmodus kostet etwa 2 bis 5 min Planung mehr **[Hochrechnung]**.
4. Stumme Aktionsszenen nutzen Wan 2.2 mit Lightning. Das wirkt laut Berichten oft wie Zeitlupe **[Vermutung]**.
5. Laufende Projekte aus 0.16 behalten ihre Stimmen, Szenenlängen und Bewegungstexte. So wird nichts doppelt gerechnet. Die Verbesserungen siehst du deshalb nur in **neuen** Filmen oder mit „Neue Fassung“.

## 3d. Was 0.18.0 nach deinen Wünschen und deinem Feedback ändert

| Dein Punkt | Ursache | Änderung |
| --- | --- | --- |
| „höchstens 8 Einträge, nicht 13“ | **[Sicher]** Feste Grenze von 8 Figuren an drei Stellen im Code. | Grenze 30 an einer Stelle. Test mit 13 Figuren. |
| Restzeit fehlt („nach drei fertigen Abschnitten“) | **[Sicher]** Die Schätzung wartete auf drei fertige Abschnitte derselben Art. Sprech- und Bewegungsabschnitte wurden gemischt. | Getrennte Schätzung pro Art. Vorher Schätzung aus früheren Filmen, so beschriftet. |
| 5-mal bearbeitet, 5-mal dasselbe Bild | **[Sicher]** Neue Runden änderten den Bildtext kaum, deine Notiz stand ganz hinten. **[Vermutung]** Das 4-Schritt-Bildmodell ändert sich mit dem Zufallswert wenig. | Notiz steht ganz vorn. Jede Runde bekommt eine andere Bildgestaltung (Blickwinkel, Licht, Ausschnitt). |
| Musik nicht regelbar | **[Sicher]** Kein Regler in der neuen Oberfläche. Mit Autopilot gab es keinen Ton-Stopp. | Regler für Musik, Geräusche, Umgebung. Fertiger Film: „Lautstärke und Ton ändern“, der Autopilot wartet auf dich. |
| Autopilot nur noch schrittweise | **[Sicher]** Ein laufender Schritt speicherte seine alte Kopie des Projekts und schaltete den Autopilot zurück. Test zeigt den Fehler im alten Code. | Schalter liegt neben dem Projekt (wie Pause). |
| Benachrichtigung, „Sir Cay“ | – | Telegram, ntfy oder Browser. Lebendige Texte mit Emojis, Titelbild als Vorschau, Anrede änderbar. |
| Ausdruck aus dem Upload friert ein | **[Sicher]** Das Bild wurde 1:1 als Figur benutzt. | Einmal mit neutralem Gesicht nachgezeichnet. „Bild genau so verwenden“ bleibt wählbar. |
| Ping-Pong-Schnitt | **[Sicher]** Jede Zeile war eine eigene Einstellung. | Gesprächsblöcke, Reaktions- und Orts-Einstellungen. **[Hochrechnung]** Bei deinem Film ~58 → ~42 GPU-Minuten. |
| Figuren-Bibliothek, Titelbild, Render-Uhr | – | Gebaut, siehe README. |
| „Mehr als acht Figuren“ bei SpongeBob-Serie (0.17) | **[Sicher]** Eine Figur unter mehreren Schreibweisen wurde mehrfach gezählt (16 Namen für 8 Figuren). | Schreibweisen werden zusammengeführt; Test mit deiner Liste ergibt 8. |
| „SourceNote … at most 2200 characters“ (0.17) | **[Sicher]** Ollama hält die Längenvorgabe nicht immer ein; ein zu langer KI-Text brach die Planung ab. | Zu lange KI-Texte werden am Satzende gekürzt, nirgends ein Abbruch. |
| 6 Folgen gewählt, 5 erstellt | **[Vermutung]** Ursache nicht belegt, Fehlerbericht fehlt. | Planung hält vor dem ersten Bild an, wenn die Zahl nicht stimmt. |
| Pausierte/fertige Projekte nicht löschbar | **[Sicher]** 0.17 hatte in der neuen Oberfläche kein Löschen. | Papierkorb + „Endgültig löschen“ (Videos nur nach zweiter Bestätigung). |
| Eigenes Skript einfügen | – | „Mein Drehbuch“: .md/.txt oder einfügen, jedes Wort bleibt, bis 3 Minuten pro Folge. PDF nicht (Text kopieren). |
| Figuren pro Folge anders anziehen | – | „Aussehen pro Folge“: Gesicht und Körper gleich, Kleidung je Folge; Figurencheck zeigt die Varianten. |

**Ehrliche Grenzen:**
1. Nichts davon lief auf deiner Grafikkarte. Ob Wan bei Reaktions-Einstellungen den Mund des Zuhörers geschlossen hält, zeigt erst dein Film **[Vermutung]**.
2. Ob die neuen Bildrunden mit dem echten FLUX-Modell deutlich anders aussehen, ist nicht gemessen.
3. Telegram und ntfy sind nur gegen einen Testserver geprüft, nicht gegen die echten Dienste.
4. Laufende Projekte behalten den 0.17-Schnitt. Neuerungen gibt es in neuen Filmen und mit „Neue Fassung“.
5. „Mein Drehbuch“ und „Aussehen pro Folge“ sind nur mit Test-KI geprüft. Wie gut FLUX das Gesicht bei neuer Kleidung hält, zeigt erst dein PC.

## 3e. Neu in 0.18.1: Arbeiten von unterwegs

1. **Unterwegs-Zugriff** über Tailscale (kostenlos, privates Netz nur aus deinen Geräten). Zahnrad → Unterwegs-Zugriff, nur am PC ein- und ausschaltbar. Das Studio nimmt außer `127.0.0.1` genau die eine Tailscale-Adresse deines PCs an, nie Tailscale Funnel (öffentlich).
2. **Nicht auf deinem PC geprüft:** ob WSL `tailscale.exe` starten darf, ob Tailscale den Studio-Port in WSL erreicht und wie es übers Handynetz läuft. Geprüft nur mit einem nachgebauten Tailscale.
3. Nicht über GitHub oder fremde Server: Projekte bleiben auf deinem PC.

## 3f. Neu in 0.19.0

1. **Tempo realistisch:** Rund 85–90 % der Zeit ist die Lippen-Animation. 0.19 spart dort rechnerisch etwa 20 % der Bilder und alle Leerlauf-Pausen. Eine 6×120-s-Serie dauert damit eher 8 als 11,5 Stunden [Hochrechnung].
2. **Deutlich schneller nur mit Entscheidung:** Sprechszenen in 480×832 statt 576×1024 wären rechnerisch etwa 40 % schneller, aber weniger scharf. Erst nach einem Sichtvergleich am Handy.
3. **Speicher:** WSL nutzt 48 von 64 GB, die Auslagerung ist voll. Laut Messung bremst das die Fenster nicht, kann aber die Stabilität kosten.

## 4b. Nächste Zeithebel nach deinem Test (alle kostenlos)

| Hebel | Erwartung [Hochrechnung] | Risiko |
| --- | --- | --- |
| fp16-Rechnung (fp16_fast) wie in Kijais Beispiel | −20 bis −30 % pro Durchlauf | Farb- oder Schwarzbilder möglich, nur mit Probe |
| SageAttention 2.2 statt 1.0.6 (selbst gebaut in WSL) | −10 bis −20 % | Einrichtung braucht CUDA-Toolkit |
| Entwurf 480×832 | 1,6- bis 1,8-mal schneller | weniger Detail |
| Audio-Führung ganz aus (1.0) | weitere −20 % | Lippen eventuell schwächer |

## 4. Was eine Minute Film dann kostet [Hochrechnung]

| Qualität | heute (gemessen) | mit 0.15 + Turbo, wenn der RAM stabil ist |
| --- | --- | --- |
| Standard 576×1024 | 1,8 bis 5,4 h | **etwa 50 bis 90 min** |
| Entwurf 480×832 | (noch nicht gemessen) | **etwa 35 bis 60 min** |

Mit Autopilot rund um die Uhr wären das bei Standard etwa 15 bis 25 Minuten fertigen Film pro Tag. **Diese Werte muss der nächste Test bestätigen.**

## 5. Rechtlicher Hinweis

Figuren wie Phineas und Ferb gehören Disney. Fan-Videos damit können auf TikTok und YouTube gesperrt oder von der Monetarisierung ausgeschlossen werden. Eigene Figuren im selben Look sind sicherer.

## 6. Nächste Schritte

1. 0.18.0 installieren (kein Neustart nötig).
2. Kurzer Test: 60 s, Standard, Autopilot an, Titelbild am Anfang. Achten auf Titelbild, Gesprächsblöcke, Untertitel, Lautstärke.
3. Danach der große Testlauf (6 Folgen, 13 Figuren).
4. Video (Original aus 03_Fertige_Videos) und Diagnose schicken. Daraus: GPU-Minuten pro Film, Sprachanteil, ob Zuhörer den Mund zu halten.
5. Entscheidung zum Arbeiten von unterwegs, dann 0.19.
