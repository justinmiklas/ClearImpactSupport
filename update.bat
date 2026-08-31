@echo off
setlocal
cd /d "%~dp0"

echo ===============================================
echo    Clear Impact Support Bot - Update Knowledge
echo ===============================================
echo.
echo This refreshes the bot from your HubSpot help center.
echo It is safe to run anytime and may take a few minutes.
echo.

echo Step 1 of 2: Downloading the latest articles from HubSpot...
echo.
python hubspot_export.py --clean
if errorlevel 1 goto :failed
echo.

echo Step 2 of 2: Updating the bot's knowledge base...
echo.
python kb_sync.py
if errorlevel 1 goto :failed
echo.

echo ===============================================
echo    Done. The bot is now up to date.
echo ===============================================
echo.
echo You can close this window.
pause
exit /b 0

:failed
echo.
echo ***********************************************
echo    Something went wrong and the update stopped.
echo    Good news: nothing was broken. The bot still
echo    works with the knowledge it already has.
echo    Please copy the messages above to get help.
echo ***********************************************
echo.
pause
exit /b 1
