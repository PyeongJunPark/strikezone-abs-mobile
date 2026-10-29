param([string]$JdkPath = $env:JAVA_HOME, [string]$SdkPath = $env:ANDROID_HOME)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
if (-not $JdkPath) {
    $candidate = Get-ChildItem (Join-Path $env:USERPROFILE '.local/share/strikezone-tools/jdk17') -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName 'bin/java.exe') } | Select-Object -First 1
    if ($candidate) { $JdkPath = $candidate.FullName }
}
if (-not $SdkPath) { $SdkPath = Join-Path $env:LOCALAPPDATA 'Android/Sdk' }
if (-not $JdkPath -or -not (Test-Path (Join-Path $JdkPath 'bin/java.exe'))) {
    throw 'Pass -JdkPath with your JDK 17 installation directory.'
}
if (-not (Test-Path (Join-Path $SdkPath 'platforms/android-35/android.jar'))) {
    throw 'Install Android SDK Platform 35 and pass -SdkPath with the SDK directory.'
}
$previousJava = $env:JAVA_HOME
$previousAndroid = $env:ANDROID_HOME
Push-Location (Join-Path $repoRoot 'android')
try {
    $env:JAVA_HOME = $JdkPath
    $env:ANDROID_HOME = $SdkPath
    & ./gradlew.bat assembleDebug --console=plain
    if ($LASTEXITCODE -ne 0) { throw 'Android build failed' }
} finally {
    $env:JAVA_HOME = $previousJava
    $env:ANDROID_HOME = $previousAndroid
    Pop-Location
}
