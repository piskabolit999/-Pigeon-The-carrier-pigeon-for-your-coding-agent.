# Removes the autostart task that the bot installs for itself on first run,
# and stops the running bot process.
# Usage: powershell -ExecutionPolicy Bypass -File .\uninstall_autostart.ps1

$ErrorActionPreference = "SilentlyContinue"
$TaskName = "ClineTelegramBot"

Stop-ScheduledTask -TaskName $TaskName
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*telegram-cline-bot*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "Removed autostart task '$TaskName' and stopped the bot."

