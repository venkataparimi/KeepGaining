# TimescaleDB Local Windows Installation Script
# Run this in PowerShell as Administrator

Write-Host "🚀 TimescaleDB Windows Installation" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "❌ Please run this script as Administrator" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

# Step 1: Check if PostgreSQL is installed
Write-Host "`n📦 Checking PostgreSQL installation..." -ForegroundColor Yellow

$pgService = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue
if (-not $pgService) {
    Write-Host "❌ PostgreSQL not found. Installing PostgreSQL 16..." -ForegroundColor Red
    
    # Download PostgreSQL installer
    $pgUrl = "https://get.enterprisedb.com/postgresql/postgresql-16.1-1-windows-x64.exe"
    $pgInstaller = "$env:TEMP\postgresql-16.1-1-windows-x64.exe"
    
    Write-Host "Downloading PostgreSQL 16..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $pgUrl -OutFile $pgInstaller
    
    Write-Host "Installing PostgreSQL 16..." -ForegroundColor Yellow
    Write-Host "⚠️  Use password: 'password' for postgres user (or change in .env later)" -ForegroundColor Yellow
    
    # Run installer silently
    Start-Process -FilePath $pgInstaller -ArgumentList @(
        "--mode", "unattended",
        "--superpassword", "password",
        "--serverport", "5432"
    ) -Wait
    
    Write-Host "✅ PostgreSQL 16 installed" -ForegroundColor Green
} else {
    Write-Host "✅ PostgreSQL already installed" -ForegroundColor Green
}

# Step 2: Download and install TimescaleDB
Write-Host "`n📦 Installing TimescaleDB extension..." -ForegroundColor Yellow

$tsdbUrl = "https://github.com/timescale/timescaledb/releases/download/2.13.0/timescaledb-postgresql-16-2.13.0-windows-amd64.zip"
$tsdbZip = "$env:TEMP\timescaledb-pg16.zip"
$tsdbExtract = "$env:TEMP\timescaledb-pg16"

# Download TimescaleDB
Write-Host "Downloading TimescaleDB 2.13.0..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $tsdbUrl -OutFile $tsdbZip

# Extract
Write-Host "Extracting TimescaleDB..." -ForegroundColor Yellow
Expand-Archive -Path $tsdbZip -DestinationPath $tsdbExtract -Force

# Find PostgreSQL installation directory
$pgPath = "C:\Program Files\PostgreSQL\16"
if (-not (Test-Path $pgPath)) {
    $pgPath = "C:\Program Files\PostgreSQL\15"
}
if (-not (Test-Path $pgPath)) {
    Write-Host "❌ Could not find PostgreSQL installation" -ForegroundColor Red
    Write-Host "Please install PostgreSQL manually from: https://www.postgresql.org/download/windows/" -ForegroundColor Yellow
    exit 1
}

Write-Host "Found PostgreSQL at: $pgPath" -ForegroundColor Green

# Copy TimescaleDB files
Write-Host "Installing TimescaleDB files..." -ForegroundColor Yellow
$tsdbLib = Get-ChildItem -Path $tsdbExtract -Recurse -Filter "timescaledb*.dll" | Select-Object -First 1
if ($tsdbLib) {
    Copy-Item -Path $tsdbLib.FullName -Destination "$pgPath\lib\" -Force
    Write-Host "✅ Copied TimescaleDB library" -ForegroundColor Green
}

$tsdbControl = Get-ChildItem -Path $tsdbExtract -Recurse -Filter "timescaledb*.control" | Select-Object -First 1
if ($tsdbControl) {
    Copy-Item -Path $tsdbControl.FullName -Destination "$pgPath\share\extension\" -Force
    Write-Host "✅ Copied TimescaleDB control file" -ForegroundColor Green
}

$tsdbSql = Get-ChildItem -Path $tsdbExtract -Recurse -Filter "timescaledb*.sql"
foreach ($sql in $tsdbSql) {
    Copy-Item -Path $sql.FullName -Destination "$pgPath\share\extension\" -Force
}
Write-Host "✅ Copied TimescaleDB SQL files" -ForegroundColor Green

# Step 3: Update PostgreSQL configuration
Write-Host "`n⚙️  Configuring PostgreSQL for TimescaleDB..." -ForegroundColor Yellow

$pgDataPath = "$pgPath\data"
$pgConfPath = "$pgDataPath\postgresql.conf"

if (Test-Path $pgConfPath) {
    # Backup original config
    Copy-Item -Path $pgConfPath -Destination "$pgConfPath.backup" -Force
    Write-Host "✅ Backed up postgresql.conf" -ForegroundColor Green
    
    # Add TimescaleDB to shared_preload_libraries
    $pgConf = Get-Content $pgConfPath
    $hasTimescale = $pgConf | Select-String -Pattern "shared_preload_libraries.*timescaledb"
    
    if (-not $hasTimescale) {
        Write-Host "Adding TimescaleDB to shared_preload_libraries..." -ForegroundColor Yellow
        $newConf = $pgConf -replace "^#?shared_preload_libraries = ''", "shared_preload_libraries = 'timescaledb'"
        $newConf | Set-Content $pgConfPath
        Write-Host "✅ Updated postgresql.conf" -ForegroundColor Green
    } else {
        Write-Host "✅ TimescaleDB already configured" -ForegroundColor Green
    }
} else {
    Write-Host "⚠️  Could not find postgresql.conf at: $pgConfPath" -ForegroundColor Yellow
}

# Step 4: Restart PostgreSQL
Write-Host "`n🔄 Restarting PostgreSQL service..." -ForegroundColor Yellow

$pgService = Get-Service -Name "postgresql*" | Select-Object -First 1
if ($pgService) {
    Restart-Service -Name $pgService.Name -Force
    Start-Sleep -Seconds 5
    Write-Host "✅ PostgreSQL restarted" -ForegroundColor Green
} else {
    Write-Host "⚠️  Could not find PostgreSQL service" -ForegroundColor Yellow
}

# Step 5: Enable TimescaleDB extension in database
Write-Host "`n🔧 Enabling TimescaleDB extension in database..." -ForegroundColor Yellow

$env:PGPASSWORD = "password"
$psqlPath = "$pgPath\bin\psql.exe"

if (Test-Path $psqlPath) {
    # Create database if it doesn't exist
    & $psqlPath -U postgres -c "CREATE DATABASE keepgaining;" 2>$null
    
    # Enable extension
    $result = & $psqlPath -U postgres -d keepgaining -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;" 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ TimescaleDB extension enabled" -ForegroundColor Green
        
        # Verify installation
        $version = & $psqlPath -U postgres -d keepgaining -t -c "SELECT extversion FROM pg_extension WHERE extname='timescaledb';"
        Write-Host "✅ TimescaleDB version: $($version.Trim())" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to enable TimescaleDB extension" -ForegroundColor Red
        Write-Host $result -ForegroundColor Red
    }
} else {
    Write-Host "⚠️  Could not find psql.exe at: $psqlPath" -ForegroundColor Yellow
}

# Step 6: Update .env file
Write-Host "`n📝 Updating .env configuration..." -ForegroundColor Yellow

$envPath = "C:\code\KeepGaining\backend\.env"
if (Test-Path $envPath) {
    $envContent = Get-Content $envPath
    $newEnv = $envContent -replace "DATABASE_URL=.*", "DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/keepgaining"
    $newEnv | Set-Content $envPath
    Write-Host "✅ Updated .env with local database connection" -ForegroundColor Green
} else {
    Write-Host "⚠️  .env file not found at: $envPath" -ForegroundColor Yellow
}

# Cleanup
Remove-Item -Path $tsdbZip -Force -ErrorAction SilentlyContinue
Remove-Item -Path $tsdbExtract -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "`n✅ Installation Complete!" -ForegroundColor Green
Write-Host "`n📋 Next Steps:" -ForegroundColor Cyan
Write-Host "1. cd C:\code\KeepGaining\backend" -ForegroundColor White
Write-Host "2. alembic upgrade head" -ForegroundColor White
Write-Host "3. python -m uvicorn app.main:app --reload" -ForegroundColor White
Write-Host "`n🎉 TimescaleDB is ready to use!" -ForegroundColor Cyan
