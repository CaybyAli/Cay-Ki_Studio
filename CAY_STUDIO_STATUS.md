# Cay Studio – Arbeitsstand

Stand: 15.10.2026 (0.17.0) · Branch `claude/new-session-s0p05c`

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

## 0.13.3 (12.10.2026) – Cay: Ton da, klingt billig; 15-s-Film lädt > 30 min
Belegt aus Cays Bildschirmfoto + Code:
- **[Sicher]** „13/80“: Profil `high` → InfiniteTalk 40 Schritte × 2 Fenster (129 Frames, Fenster 81) in 720×1280 mit einem **480P**-Modell, `blocks_to_swap=20`.
- **[Sicher, Foto]** 21 min ohne neuen Rechenschritt bei 12 % GPU, Windows-RAM frei 5,9 GB → Stillstand, kein langsames Rechnen.
- **[Vermutung]** Ursache: Speicher (Auslagerung zwischen GPU und RAM). Beweis fehlt: `nvidia-smi` während des Hängens.
- **[Sicher, Code]** Kein Abbruch eines ComfyUI-Auftrags möglich; „unklare“ Aufträge nach Neustart blockieren das Projekt für immer.
- **[Hochrechnung]** Ohne Hänger ~37 s/Schritt → 80 Schritte ≈ 50 min pro 5-s-Abschnitt → 15 s ≈ 3 h, 60 s ≈ 13 h.

Änderungen: `POST /api/factory/{rid}/abort-step` (nur eigene Aufträge; unbekannte nach Neustart verworfen; fertige nie), Render-Schleife verlässt abgebrochene Abschnitte sauber, Hänger-Karte (>10 min), Knopf für unklare Aufträge, Standard `fast`, Diagnose mit LoRAs/GPU/ComfyUI-Log, Überschrift „Dein Film entsteht“.
Prüfung: `tests/manual/abort_step_check.py` 11/11, Chromium-Bild der Karte, pytest 14/14.
Stimmen „billig“: offen. Hörbar billig wirken sicher auch die synthetische Sinus-Musik und das Rausch-Ambiente aus `factory_audio.py` **[Sicher, Code; Wirkung Vermutung]**.

## 12.10.2026 – Rückmeldung nach 0.13.3
- **[Sicher, nvidia-smi von Cay]** 22 703 / 24 564 MiB Grafikspeicher belegt, 3 % GPU, 64 W, P2 → Speicher voll, keine Rechnung. Stützt die Speicher-Ursache des Hängens.
- **[Sicher, Code]** Update unmöglich, solange ein Abschnitt hängt: `/api/system/maintenance` lehnt bei `factory.busy` ab (409); Pause hilft nicht. Lösung: PC-Neustart, dann Update.
- Updater-Meldung nennt das jetzt; `Cay_Studio_Update.cmd` schreibt `Cay_Studio_Updateprotokoll.txt`. Payload unverändert 0.13.3.
- **[Vermutung]** Wallpaper Engine belegt zusätzlich GPU; unter WDDM nicht messbar (N/A).

## 13.10.2026 – Cay: 15-s-Film mit „Schnell“ fertig
- **[Sicher, Foto]** Mit `fast`: GPU 99 %, letzter Fortschritt 0 s → kein Hänger mehr. Dialog vorhanden, Bildqualität laut Cay sehr gut; manchmal fehlt ein Arm.
- **[Sicher, Foto Task-Manager]** VmmemWSL 44,6 GB RAM; Windows-RAM 86 % belegt.
- **Offen:** Gesamtzeit und Anteil je Schritt unbekannt → Diagnose mit Zeittabelle. Inhalt laut Cay: „eine Person ein Satz, Schnitt, andere Person ein Satz“ → Wörter/Sprechanteil aus Diagnose prüfen.
- **[Sicher, Code]** Mundbewegung läuft mit `cfg=1` in allen Profilen → Negativ-Prompt („missing arm“) wirkt dort nicht.
- 0.13.4: Messung `Stimmgestaltung` und `Sprache · <engine>`; Diagnose-Zeittabelle.

## 0.14.0 (13.10.2026) – großer Umbau auf Cays Wunsch
Grundlage: Diagnose des Keks-Films (Animation 82,7 von 87,5 min; ComfyUI 55 s/Schritt; schnellster Abschnitt 528 s, Mittel 20,7 min).
Geändert: Profile Entwurf 480×832 / Standard 576×1024; eine Sprechszene = ein Auftrag; 25 FPS ohne Umrechnung von Sprechszenen; Autopilot; Serien-Cliffhanger + „Teil X/Y“ + Beschreibung; −14 LUFS; neue Oberfläche `web/app2` (alt unter /classic).
Prüfung: pytest 25; `tests/manual/ui_check.py` 16/16, `autopilot_check.py` 5/5, `abort_step_check.py` 11/11.
Plan und Grenzen: `CAY_STUDIO_PLAN.md`.

## 0.15.0 (14.10.2026) – Cay: Knöpfe überlappen, Beispielbilder fehlen, Filme-Reiter weg, 1 min darf keine 10 h dauern
- Überlappung nachgestellt (0 px Abstand) und behoben; Look-Vorlagen (bis 4, JPG/WebP → PNG im Browser); Look „Knete“; Filme-Reiter entfernt; Warteschlangenplatz; Schätzung aus Messwerten.
- Turbo (`turbo.py`): SageAttention 1.0.6 per pip --no-deps, CUDA-Probe, aktiv erst nach ComfyUI-Neustart, Abschalten bei fehlgeschlagenem Abschnitt.
- Diagnose „PC als Team“: RAM/Swap/WSL-Einstellung/PCIe/Modell-Dateisystem/ComfyUI-Zeiten.
- Prüfung: pytest 28, ui_check 20/20, queue_check 3/3, autopilot 5/5, abort 11/11.

## 0.16.0 (14.10.2026) – Cay: Qualität top, aber 5 h; Vorlagen-Personen im Film; SpongeBob wechselt Gesicht; statisch, Zeitlupe; Planung ohne Ziel
- `cast_design.py` (neu): Figur aus Text (ohne Vorlage), dann Stilübertragung mit Vorlagen; Szenen nur mit Figurenbildern; `invalidate()` zeichnet alle Szenen einer geänderten Figur neu (vorher nur eine).
- `CastPlan.original` + Planungsregel für bekannte Figuren; Endpunkte `POST /cast/redo`, `GET /cast-image/{i}`; UI „Deine Figuren“.
- `StorySpine` (Ziel des Films) vor jedem Drehbuch, an Drehbuch, Prüfung, Überarbeitung und Dialogergänzung übergeben; UI-Karte „Ziel des Films“.
- Tempo: `DIRECTION` mit Handlung pro Äußerung und kurzen Sätzen; `motion_direction`, InfiniteTalk-Prompt und Schuss/Gegenschuss-Prompts lebendig; `audio_layout` Sprache ab 0,08 s, Restzeit zuerst in ohnehin gerechnete Lippensync-Bilder (max. 1 s), dann in stumme Handlungsszenen.
- `render_order`: Sprechszenen vor Bewegungsszenen (render() entlädt bei Familienwechsel alle Modelle).
- Diagnose: Figurenherkunft, Lippensync-Rechenfenster, Minuten pro Fenster, Modellwechsel.
- Prüfung: pytest 42 (neu 14 in `test_identity_pacing.py`), ui_check 23/23, autopilot 5/5, abort 11/11, queue 3/3, Installation trocken bytegleich.
- Nicht geprüft: echtes Bild/Video auf Cays GPU, Wirkung der neuen Prompts, Zeitgewinn.

## 0.16.1 (14.10.2026) – Cay: „Nachbearbeitung: Tonmischung unvollständig; keine Freigabe“ (Projekt „Der Einbruch im Krusty-Versteck“, 60 s, Standard)
- Ursache [Sicher, nachgestellt mit FFmpeg 6.1]: `loudnorm` verschiebt die Ausgabe-Zeitstempel; `-t`/`atrim` schneiden danach zu früh. 10,04 s → 9,98 s, 60,12 s → 60,04 s. Bis 0.15 war die Länge meist genau das Ziel (60,0 s, ganze Zehntel), daher unbemerkt. 0.16 rundet jede Szene auf ganze Videobilder → 60,12/60,16 s → Prüfung > 30 ms schlägt an.
- Fix `factory_audio.exact()`: vor `loudnorm` 0,5 s Stille, danach `asetpts=N/SR/TB` und `atrim` auf exakte Länge (Dialog, Musik, Endmischung).
- Test `tests/test_mix_length.py` (echtes FFmpeg): vorher 2 von 3 rot, jetzt 3/3; 60-s-Zufallsmischungen 60,16 s OK. pytest gesamt 45.
- Fehlerbericht: Planung ~3 min, 28 Bilder 130 s, Stimmgestaltung 105 s, Sprache 49 s. Noch keine Animationszeit gemessen. WSL 50,5 GB, Auslagerung 0.

## 0.17.0 (14.10.2026) – Cay: Mund bewegt sich ohne Text, Text langweilig/sinnlos, fremde Figuren, keine Spannung, monotone Stimmen, ~2 h
Analyse: Video (Einzelbilder, silencedetect: 2,2–4,5 s Stille nach jeder Zeile, Sprachanteil 0,41), Diagnose 0.16.1, Workflow mit 5 Code-Prüfern + TTS-Recherche + Render-Recherche + Quelltext WanVideoWrapper 088128b.
- `screenplay.py` (neu): Drehbuch als Klartext-Gespräch (`Factory.write`, think mit Rückfall, Prüfung + Rückgabe der Fehler, Script Doctor, Rückfall auf Entwurf), deterministischer Schnitt pro Sprecherwechsel, AKTION-Zeilen als stumme Szenen, `ShotVisuals`-JSON für Bild/Bewegung, `sanitize` streicht Satzteile über Figuren außerhalb des Bilds. Alter Szenenplaner nur noch für Filme ohne Sprache.
- `cast_design.py`: eigener Name statt Serie, keine Stilübertragung für bekannte Figuren, Körperbau zuerst, `scene_text`, `strip_names` auch im Stiltext; Zustand `cast_review` (Idea.cast_check), Endpunkte `cast/approve`, `cast/image`, `cast/redo` (auch in cast_review).
- `factory_timing.py`: `talk_plan` (keine Pause nach letzter Zeile, Einpassen knapp über Fenstergrenze), `fill_target` (Sprechszene max. +0,35 s, Rest stumme Szenen), Bericht mit `silent_shots`.
- Animation: `motion_direction` neu (nur sichtbare Figur, Mund zu in Pausen), alter Text als `motion_direction_v16`/`V16_SUFFIX` für Projekte, die schon rendern (`prompt_policy`); `cay_audio_cfg_steps=1` über `comfy_sampler_compat.py` (Audio-CFG nur Schritt 1: 8→5 Durchläufe/Fenster; Versionskennung bleibt 13.0, sonst würden alte Fenster neu gerechnet).
- Stimmen: `EMOTION_TEXTS`, `performance_key` 16 Kategorien, Cartoon-Beschreibung, Clone temp 0.9/top_p 1/top_k 50, Best-of-2 nach `prosody_score`, Chatterbox-Rezept, `level_db` in der Mischung, sanfterer Kompressor.
- UI: Figurenprüfung, eigenes Figurenbild, Prüfzeile (Wörter, Sprachanteil, Pause, Rechenblöcke), Status „Wartet auf dich“ bei Autopilot-Stopp. Diagnose: Drehbuch, Aufmerksamkeit/Audio-Führung, Knotenzeiten.
- Nicht geprüft: alles auf der GPU (Bild, Lippen, Stimmen, Zeitgewinn).

### 0.17.0 – fünf unabhängige Prüfrunden (15.10.2026)
- Alte Projekte rechnen nichts doppelt: je Projekt festgehalten `prompt_policy` (Bewegungstext), `timing_layout` (Szenenlängen 0.16), `voice_policy` (Stimmen/Sampling/Signaturen 0.16). Beleg: `tests/test_compat_016.py` vergleicht mit Referenz aus 0.16.1 (git `9fbc214`, `tests/fixtures/v16_reference.json`): Layout, Lippen-Graph vor/nach Neustart, Sampler-Version, Stimmdateinamen und Modellaufrufe. Gegenprobe: 5 absichtlich eingebaute Fehler werden erkannt.
- Neue schnelle Lippen-Animation ohne ComfyUI-Neustart: klare Meldung „PC neu starten“ statt stiller Doppelrechnung; Installer sagt das am Ende.
- Namen: „Mr. Krabs“ bleibt ein Name (kein Satzende), „Captain Hook“ wird entfernt, „Captain Smee“ bleibt; Groß-/Kleinschreibung (Spongebob, oma).
- Stimmen: „neugierig/beschreibend/flach/gescheitert“ nicht mehr als Triumph/Schrei/Freude; misslungene Gefühlsprobe → Grundstimme statt Abbruch; Tonhöhenmessung bis 1000 Hz ohne Oktavsprünge; Flüstern −2 dB.
- Neue App „Text ändern“ behält Sprechhaltung und Pause; klassische Ansicht zeigt „Figuren prüfen“.
- Runde 3 (Gegenprüfung, 3 bestätigt, 8 widerlegt): überlappende Namen – der längere gewinnt („Tims Oma“ vor „Tim“); handelt die unsichtbare Figur („Mr. Krabs packt SpongeBob“), fällt der Satzteil ganz weg; Titel/„und“ vor gestrichenem Namen und hängendes „while“ werden mit entfernt; alte Einzelzeilen behalten im Editor ihre Sprechhaltung.
- Runde 4 (Namensfilter, 11 Funde bestätigt): Filter strukturiert neu – Namenslisten („Phineas und Ferb bauen“ → „Ferb bauen“), Name nach Präposition oder mit Besitz-s ist kein Subjekt („Hinter Thaddäus schleicht SpongeBob“), „… und Patrick weint“ ist ein eigener Satzteil, Nebensätze (as/when/als/weil …) nur vor neuem Subjekt, Relativsätze folgen der zuletzt genannten Figur („…, who dodges“ → „Peter Pan dodges“), deutsche Verbteile („macht die Tür zu“) bleiben, kurze Namensteile („Oma“ für „Tims Oma“), „Herrn Müller“. Beleg: 1973 Durchläufe über ~170 Prüfersätze ohne einen Fall mit unsichtbarer Figur im Text; `tests/test_names_017.py` (36 Fälle).
- Runde 5 (23 Funde): Mustererkennung allein hat einen endlosen Rest. Deshalb jetzt dreistufig: (1) die KI bekommt Bildtexte mit Figuren außerhalb des Bildes zurück und schreibt nur diese Einstellungen neu (`repair_visuals`, lokal, ~1 min); (2) mehr Schreibweisen: Originalname (Squidward für Thaddäus), Grandma/Mom/Dad für Oma/Mama/Papa, Thaddaeus, Mr Krabs, Bowser Jr, Tinkerbell, „Tim's Oma“, Herrn Müller, kurze Vornamen (Kim, Ron); (3) Filter als letztes Netz: Aufzählungen nur am Satzanfang oder vor Satzende/Artikel, Nebensatz-Wörter (wie, where, but, aber, und dann), Fortsetzungen eines gestrichenen Satzteils, Pronomen-Sätze, vorangestellte Nebensätze, Beinamen („the Platypus“).
  Beleg auf der Prüfer-Sammlung (251 Sätze, 4471 Durchläufe, jedes Handlungswort einer Figur zugeordnet): unsichtbare Figur genannt 37 → 0, fremde Handlung behalten 727 → 36, eigene Handlung verloren 172 → 45 (Stand Runde 4 → jetzt). Ältere Sammlung: 1973 Durchläufe, 0 unsichtbare Figuren.
- Schlussprüfung (Abstürze/Einbindung, 2 bestätigt, behoben): Fällt die KI-Rückfrage aus (Zeitüberschreitung, Ollama-Fehler), bleibt die erste Antwort gespeichert und die Planung läuft weiter; Namen mit „:“, „–“ oder „Dann“ werden nicht zerschnitten. Alte Projekte (prompt_policy 16) unverändert (`tests/test_compat_016.py`).
- Prüfungen: `pytest` 162 bestanden; Browser `ui_check.py` 30/30, `autopilot_check.py` 5/5, `abort_step_check.py` 11/11, `queue_check.py` bestanden; Update gebaut (Payload `139e893c`, 78 Dateien) und Trockeninstallation bytegleich, neuer Release-Ordner.

## Nächster konkreter Schritt
Cay: 0.17.0 installieren, PC neu starten, SpongeBob-Film 60 s Standard mit Autopilot und Figurenprüfung, Video + Diagnose schicken.

## Reihenfolge danach
Siehe `CAY_STUDIO_PLAN.md`, Abschnitt 6.
