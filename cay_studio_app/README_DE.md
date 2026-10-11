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
