# Cay Studio – Arbeitsstand

Stand: 11.10.2026 · Branch `claude/new-session-s0p05c`

## Ziel
Zuerst: keine unbemerkt fehlenden Stimmen. Danach Stimmqualität, Renderzeit, Lippensynchronität, Figurentausch, Story.

## Umgebung dieser Sitzung
- Cloud-Container. **Kein** Zugriff auf Cays PC, WSL, RTX 4090, ComfyUI, Ollama, Projekte oder Modelle.
- Repo enthielt nur das Update-Paket 0.13.0. Quellen daraus nach `cay_studio_app/` entpackt (Commit `e3d4b48`, unverändert).
- Installierte Version auf Cays PC: **unbekannt** (zuletzt geliefert 0.13.0).

## Bestätigte Ursachen (fehlende Sprache)
1. **[Sicher, reproduziert]** `factory_audio.mix()` prüfte nur Gesamtpegel der Dialogspur (`dialogue_peak`, `dialogue_rms`). Eine stumme Zeile bzw. eine ganze stumme Figur ging durch Tonvorschau und Export.
2. **[Sicher, reproduziert]** `speech_quality.finish_voice()` akzeptierte für Zeilen mit 1–3 Wörtern eine 0,2-s-Klickaufnahme (Untergrenze Dauer 0,15 s, Peak > 0,001).
3. **[Sicher, Code]** Die stumme Aufnahme wird gecacht (Signatur ohne Aufnahme-Nummer, fester Seed). „Ton neu erzeugen“ und „Fortsetzen“ lieferten dieselbe Datei erneut.
4. **[Sicher, Code]** Export prüfte nur „Tonspur vorhanden“, nicht ob Sprache darin ist.
5. **[Vermutung]** Flüster-Emotionsprofile (Qwen `quiet`) können sehr leise Zeilen erzeugen. Jetzt als Warnung „leise“ im Bericht sichtbar; echte Werte offen.
- **Nicht nachgewiesen:** die konkrete erste Verluststelle in Cays echtem Projekt (Projektdaten/Diagnose fehlen).

## Änderungen 0.13.1
- `speech_check.py` (neu, nur Standardbibliothek): Prüfung pro Beitrag (fehlt / überdeckt = blockiert; knapp / leise = Warnung), Bericht `Sprachpruefung.json`.
- `factory_audio.mix()`: blockiert bei stummen/überdeckten Beiträgen mit Folge/Szene/Figur.
- `factory_video.finish()`: vergleicht Export mit freigegebener Mischung pro Beitrag, `Exportpruefung.json`.
- `speech_quality.finish_voice()`: verlangt hörbare Sprechzeit je Wort.
- `factory_speech.py`, `factory_tts.py`: Fehlermeldung nennt Folge/Szene/Figur; `Fehlgeschlagen.json` erlaubt gezielte Neuaufnahme nach Erzeugungsfehler.
- `factory_quality.speech_retake()` + `factory.py resume`: Fortsetzen nach Sprachfehler = neue Aufnahme nur für betroffene Zeilen (`speech_takes`). Andere Zeilen behalten Cache.
- `web/studio13.js`: Reparaturkarte auch bei Tonmischungsfehlern, mit klarer Anweisung.
- `tools/build_update.py`: baut `Cay_Studio_Update_Produktion.py` aus `cay_studio_app/` und prüft bytegleich.

## Getestete Befehle
```
python3 -m venv venv && venv/bin/pip install -r cay_studio_app/requirements.lock pytest numpy
venv/bin/python -m pytest -q tests        # 9 passed (echtes FFmpeg 6.1, synthetische Stimmen)
python3 tools/build_update.py             # 0.13.1, 69 Dateien, bytegleich geprüft
```
Messwert: Sprachprüfung 0,7 s bei 90-s-Mischung mit 30 Beiträgen (Container-CPU).

## Offen
- Update auf Cays PC installieren; echte Tonvorschau eines kurzen Projekts erzeugen; `Sprachpruefung.json` zurückschicken.
- Schwellen mit echten Qwen-Stimmen (inkl. Flüstern) prüfen.
- Lokale Transkription (z. B. Whisper) mit Textabgleich gegen abgeschnittene Sätze/falsche Wörter.
- „Ton neu erzeugen“ in der Hörvorschau erzeugt weiterhin identische Aufnahmen (gleicher Seed).
- Danach: Renderzeit-Messlauf, Stimmen-Casting/-Vergleich, Lippensync, Figurentausch, Story.

## 0.13.2 (11.10.2026) – Cay meldet: 15-s-Test wieder ohne Stimmen
Bestätigte Ursache im Code (Cays Projektdaten noch nicht gesehen):
1. **[Sicher, reproduziert]** `dialogue_density.apply_additions()` verwarf die ganze Dialogergänzung, sobald eine Szene zwei sichtbare Figuren hatte (Lippensync-Regel). 0.13.1: 0 Wörter, nur Warnung.
2. **[Sicher, Code]** `factory.llm()` lehnte solche Szenen ab. Das drängt die Planung dazu, Dialoge wegzulassen. Ein Plan ohne Dialog wurde mit einer Warnung angenommen.
3. **[Sicher, Code]** Ohne Zeilen: `quality_voices` mischt stumm, die Sprachprüfung aus 0.13.1 hat nichts zu prüfen.
4. **[Wahrscheinlich]** 15 s = 3 Szenen mit beiden Figuren im Bild → genau dieser Weg.

Änderungen: `lipsync_shots.py` (Schuss/Gegenschuss vor den Bildern, höchstens 30 Einstellungen), Planungsstopp „DIALOG FEHLT“ vor den Bildern, Stopp vor der Tonmischung für alte Projekte (Neue Fassung), UI-Reparaturkarte, `Cay_Studio_Diagnose.cmd/.py` (nur lesend).
Tests: 14 bestanden (`tests/test_dialogue_plan.py`, `tests/test_speech_check.py`).

Weitere Befunde (noch nicht geändert):
- Standardqualität `high` = 720×1280, 40 Schritte für jede Animation (`studio_quality_policy.py`, `render_studio.audio_graph`). `fast` = 4 Schritte. Wahrscheinlich Hauptgrund für 10–13 h pro 90 s.
- Oberfläche: Projektseite lädt 14 Skripte und 10 Stylesheets, 13 globale Klick-Handler, 47 Funktionsüberschreibungen in Folgeschichten.
- Seedance 2.5 / Nano Banana 2: nur kostenpflichtige Cloud (Recherche 11.10.2026). Mit der Kostenregel nicht nutzbar.

## Nächster konkreter Schritt
Cay startet `Cay_Studio_Diagnose.cmd` (altes 15-s-Projekt), installiert 0.13.2, legt ein neues 15-s-Projekt mit zwei sprechenden Figuren an und schickt beide `Cay_Studio_Diagnose.txt`.

## Reihenfolge danach
1. Stimmen auf Cays PC belegt. 2. Messlauf `fast` gegen `high` (gleiche 15-s-Szene: Zeit + Sichtprüfung). 3. Neue Oberfläche aus einem Guss (ein Ablauf, ein Skript). 4. Modellvergleich lokal (Wan 2.2, LTX-2.x, HunyuanVideo 1.5; Lizenz prüfen).
