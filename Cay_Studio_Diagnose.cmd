@echo off
setlocal
chcp 65001 >nul
title Cay Studio Diagnose
set "CAY_START_HELPER=%~dp0Cay_Studio_Diagnose.py"
echo Cay Studio Diagnose - liest nur, aendert nichts
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference='Stop'; $helper=$env:CAY_START_HELPER; if (-not (Test-Path -LiteralPath $helper)) { Write-Host 'Cay_Studio_Diagnose.py fehlt. Bitte das komplette ZIP entpacken.'; exit 1 }; $distros=@(& wsl.exe --list --quiet 2>$null); if ($LASTEXITCODE -ne 0) { Write-Host 'WSL konnte nicht abgefragt werden. Bitte Ubuntu im Startmenue oeffnen.'; exit 1 }; $chosen=$null; foreach ($entry in $distros) { $d=([string]$entry).Replace([string][char]0,'').Trim(); if (-not $d -or $d -like 'docker-desktop*') { continue }; try { & wsl.exe -d $d -u alihu --exec test -f /home/alihu/ki-video/studio/config/ablage.json 2>$null } catch { continue }; if ($LASTEXITCODE -eq 0) { $chosen=$d; break } }; if (-not $chosen) { Write-Host 'Cay Studio wurde in den vorhandenen WSL-Distributionen fuer Benutzer alihu nicht gefunden. Bitte Ausgabe von wsl -l -v schicken.'; exit 1 }; Write-Host ('WSL: '+$chosen); $windowsPath=$helper.Replace([char]92,[char]47); $linuxPath=(& wsl.exe -d $chosen -u alihu --exec wslpath -u $windowsPath); if ($LASTEXITCODE -ne 0) { throw 'Startdateipfad konnte nicht umgewandelt werden.' }; $linuxPath=([string]$linuxPath).Trim(); if (-not $linuxPath.StartsWith('/')) { throw 'WSL lieferte keinen absoluten Linux-Pfad.' }; $log=Join-Path (Split-Path -LiteralPath $helper) 'Cay_Studio_Diagnose.txt'; $ErrorActionPreference='Continue'; & wsl.exe -d $chosen -u alihu --exec /usr/bin/python3 $linuxPath 2>&1 | Tee-Object -FilePath $log; $code=$LASTEXITCODE; Write-Host ''; Write-Host ('FERTIG. Bitte diese Datei schicken: '+$log); exit $code"
echo.
echo Die Datei Cay_Studio_Diagnose.txt liegt in diesem Ordner.
pause
