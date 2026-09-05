@echo off
setlocal DisableDelayedExpansion
set "PACKAGE_ROOT=%~dp0"
if not exist "%PACKAGE_ROOT%runtime\python.exe" (
  echo Ledger cannot start its installer because the bundled runtime is missing.
  echo Re-extract the complete Ledger package and try again.
  pause
  exit /b 2
)
"%PACKAGE_ROOT%runtime\python.exe" "%PACKAGE_ROOT%desktop\windows\install.py" %*
set "INSTALL_EXIT=%ERRORLEVEL%"
if not "%INSTALL_EXIT%"=="0" pause
exit /b %INSTALL_EXIT%
