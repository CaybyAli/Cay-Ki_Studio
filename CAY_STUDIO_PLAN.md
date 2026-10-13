# Cay Studio – Plan (Stand 0.14.0, 13.10.2026)

Ziel: mehrere TikToks und Shorts pro Tag, Einzelfilme und Serien bis 12 Folgen, alles lokal und ohne laufende Kosten.

Markierung: **[Sicher]** = gemessen oder getestet · **[Hochrechnung]** = aus deinen Messwerten gerechnet · **[Vermutung]** = noch nicht belegt.

## 1. Was wir haben

| Bereich | Stand | Beleg |
| --- | --- | --- |
| Stimmen im Film | Jeder Satz wird einzeln geprüft, auch im fertigen Video | [Sicher] dein 15-s-Film: 3/3 Sätze hörbar |
| Kein stummer Film | Drehbuch ohne Dialog hält vor den Bildern an | [Sicher] Tests |
| Hängende Abschnitte | Erkennung nach 10 min, Neustart per Knopf | [Sicher] Ende-zu-Ende-Test 11/11 |
| Bildqualität | Laut dir „sehr gut“, manchmal fehlt ein Arm | deine Rückmeldung |
| Zeitbedarf | Animation = 95 % der Rechenzeit | [Sicher] 82,7 von 87,5 min |
| Planung, Bilder, Ton | zusammen unter 5 min pro 15-s-Film | [Sicher] Diagnose |

## 2. Was sich in 0.14.0 ändert

1. **Neue Oberfläche.** Drei Bereiche (Neu, Projekte, Filme), pro Projekt genau ein nächster Schritt, Hell und Dunkel, Handy-tauglich. Eine Datei statt 15 übereinander gestapelter Skripte.
2. **Autopilot.** Ohne Zwischenstopps fertig produzieren. Ton wird nur freigegeben, wenn jeder Satz hörbar ist. Fehler halten weiterhin an.
3. **Serien mit offenem Ende.** Jede Folge löst ihre Frage, endet dann mit einem Cliffhanger. Die nächste Folge greift ihn in den ersten Sekunden auf. Im Bild steht kurz „Teil 3/12“.
4. **Beschreibung zum Hochladen.** Pro Folge ein Satz und Hashtags zum Kopieren.
5. **Schneller.** Qualität „Entwurf“ (480×832, Bildgröße des Mundbewegungsmodells) und „Standard“ (576×1024). Eine Sprechszene = ein Auftrag statt 5-Sekunden-Stücken.
6. **Sauberere Bewegung.** Sprechszenen werden nicht mehr künstlich von 25 auf 30 Bilder pro Sekunde umgerechnet. Diese Umrechnung kann Arme und Hände verzerren [Vermutung als Ursache des fehlenden Arms im Video].
7. **Lauterer, klarerer Ton.** Sanfte Sprachverdichtung, Endmischung auf −14 LUFS wie bei TikTok/Shorts (vorher −23,9 dB im Mittel).

## 3. Was rausfliegt

| Raus | Warum |
| --- | --- |
| Qualität „Hoch“ (720p, 40 Schritte) in neuen Projekten | [Sicher] hing bei vollem Grafikspeicher, 80 Schritte je Abschnitt |
| „Ausgewogen“ (24 Schritte) | kein belegter Nutzen, deutlich langsamer |
| 30 Bilder pro Sekunde als Standard | Umrechnung erzeugt Verzerrungen; TikTok und Shorts nehmen 25 |
| Eingebaute Pieps-Musik als Standard | klingt billig; Musik bleibt aus, eigene Musik hochladbar |
| 15 Skript-Schichten der alten Oberfläche | widersprüchliches Verhalten; alte Oberfläche bleibt unter /classic erreichbar |

## 4. Ehrliche Grenzen

- **Seedance 2.5 / Nano Banana 2** sind kostenpflichtige Cloud-Dienste. Mit deiner Kostenregel nicht nutzbar. Lokal ist die Qualität gut, aber nicht gleichwertig.
- **Zeit [Hochrechnung]:** Standard braucht je Filmsekunde 105 s (schnellster Abschnitt) bis 326 s (dein Mittelwert) Rechenzeit. Eine Minute Film = **1,8 bis 5,4 Stunden**. Entwurf etwa halb so lang. Eine 12-teilige Serie mit 1 Minute pro Folge ist ein Projekt für mehrere Tage und Nächte.
- Die große Schwankung (9 bis über 20 Minuten pro Abschnitt) deutet auf knappen Arbeitsspeicher hin [Vermutung]: WSL belegte 44,6 GB, Windows war zu 86 % voll.
- Stimmen bleiben die lokalen Modelle (Qwen3-TTS). Lauter und klarer gemischt, aber kein ElevenLabs-Niveau.

## 5. Nächste Schritte (in dieser Reihenfolge)

1. **0.14.0 auf deinem PC:** ein 30-s-Film in „Entwurf“ und einer in „Standard“, beide mit Autopilot. Zeiten aus der Diagnose vergleichen. Prüfen: Arme stabil?
2. **Arbeitsspeicher:** ComfyUI-Zwischenspeicher und WSL-Grenze messen und, wenn belegt, die Schwankung beseitigen. Ziel: jeder Abschnitt so schnell wie der schnellste (9 min statt 20,7).
3. **Turbo (SageAttention):** schnellere Rechenart für die Grafikkarte, kostenlos. Erwartung 1,5- bis 2-fach [Vermutung]. Nur mit Messung vorher und nachher.
4. **Stimmenvergleich:** dieselben Sätze mit den lokalen Modellen, Hörproben für dich, dann Entscheidung.
5. **Figurentausch** in die neue Oberfläche holen.
