# Cay Studio – Plan (Stand 0.15.0, 14.10.2026)

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

## 4. Was eine Minute Film dann kostet [Hochrechnung]

| Qualität | heute (gemessen) | mit 0.15 + Turbo, wenn der RAM stabil ist |
| --- | --- | --- |
| Standard 576×1024 | 1,8 bis 5,4 h | **etwa 50 bis 90 min** |
| Entwurf 480×832 | (noch nicht gemessen) | **etwa 35 bis 60 min** |

Mit Autopilot rund um die Uhr wären das bei Standard etwa 15 bis 25 Minuten fertigen Film pro Tag. **Diese Werte muss der nächste Test bestätigen.**

## 5. Rechtlicher Hinweis

Figuren wie Phineas und Ferb gehören Disney. Fan-Videos damit können auf TikTok und YouTube gesperrt oder von der Monetarisierung ausgeschlossen werden. Eigene Figuren im selben Look sind sicherer.

## 6. Nächste Schritte

1. 0.15.0 installieren, **Turbo einrichten** (Zahnrad), PC einmal neu starten.
2. Einen 60-s-Film in **Entwurf** mit Autopilot rechnen lassen.
3. Diagnose schicken. Daraus entscheide ich: WSL-Speicher anpassen (nur wenn die Werte es zeigen), Turbo behalten, Zeitziel festlegen.
4. Danach: Stimmenvergleich, Figurentausch in der neuen Oberfläche.
