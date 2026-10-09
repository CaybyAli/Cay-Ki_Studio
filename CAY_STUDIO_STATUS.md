# Cay Studio – Arbeitsstand

Stand: 09.10.2026 · Branch `claude/new-session-s0p05c`

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

## Nächster konkreter Schritt
Cay installiert 0.13.1 und erzeugt bei einem bestehenden Projekt eine neue Tonvorschau; Ergebnis (Meldung oder `Sprachpruefung.json`) zurückschicken.
