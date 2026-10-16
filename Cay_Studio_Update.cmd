@echo off
setlocal
chcp 65001 >nul
title Cay Studio Update 0.18.0
set "CAY_UPDATE_FILE=%~dp0Cay_Studio_Update_Produktion.py"
echo Cay Studio 0.18.0 aktualisieren
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference='Stop'; $file=$env:CAY_UPDATE_FILE; if (-not (Test-Path -LiteralPath $file)) { Write-Host 'Update-Datei fehlt. Bitte das komplette ZIP entpacken.'; exit 1 }; $chosen=$null; foreach ($entry in @(& wsl.exe --list --quiet 2>$null)) { $d=([string]$entry).Replace([string][char]0,'').Trim(); if (-not $d -or $d -like 'docker-desktop*') { continue }; try { & wsl.exe -d $d -u alihu --exec test -f /home/alihu/ki-video/studio/config/ablage.json 2>$null } catch { continue }; if ($LASTEXITCODE -eq 0) { $chosen=$d; break } }; if (-not $chosen) { Write-Host 'Vorhandene Cay-Studio-Installation nicht gefunden. Bitte wsl -l -v ausgeben.'; exit 1 }; $win=$file.Replace([char]92,[char]47); $linux=(& wsl.exe -d $chosen -u alihu --exec wslpath -u $win); if ($LASTEXITCODE -ne 0) { throw 'Updatepfad konnte nicht umgewandelt werden.' }; $linux=([string]$linux).Trim(); if (-not $linux.StartsWith('/')) { throw 'Kein absoluter WSL-Pfad.' }; Write-Host ('WSL: '+$chosen); $log=Join-Path (Split-Path -LiteralPath $file) 'Cay_Studio_Updateprotokoll.txt'; $ErrorActionPreference='Continue'; & wsl.exe -d $chosen -u alihu --exec /home/alihu/ki-video/envs/comfyui/bin/python $linux 2>&1 | Tee-Object -FilePath $log; $code=$LASTEXITCODE; Write-Host ('Protokoll: '+$log); if ($code -eq 0) { Start-Process 'http://127.0.0.1:8787'; Write-Host 'Fertig. Im Browser Strg+F5 druecken: unten muss 0.18.0 stehen.' }; exit $code"
echo.
echo Bei beschaeftigter Produktion den aktuellen Schritt abwarten und erneut starten.
pause
