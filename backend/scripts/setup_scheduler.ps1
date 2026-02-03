# Setup Windows Task Scheduler for Daily Indicator Refresh
# Run this script as Administrator in PowerShell

$TaskName = "KeepGaining-IndicatorRefresh"
$ScriptPath = "C:\code\KeepGaining\backend\scripts\run_daily_refresh.bat"
$WorkingDir = "C:\code\KeepGaining\backend\scripts"

# 4:30 PM IST = 11:00 AM UTC (adjust based on your timezone)
# Market closes at 3:30 PM IST, giving 1 hour buffer for data to settle
$TriggerTime = "16:30"

# Create the scheduled task
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$ScriptPath`"" -WorkingDirectory $WorkingDir
$Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Register the task (requires admin privileges)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Daily refresh of technical indicators for KeepGaining trading system"

Write-Host "Scheduled task '$TaskName' created successfully!"
Write-Host "The task will run daily at $TriggerTime"
Write-Host ""
Write-Host "To verify: Open Task Scheduler and look for '$TaskName'"
Write-Host "To run manually: schtasks /Run /TN `"$TaskName`""
