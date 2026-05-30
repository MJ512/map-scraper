@echo off
echo Installing required Python packages...
pip install -r requirements.txt
echo.
echo Installing Playwright Chromium Browser...
python -m playwright install chromium
echo.
echo Setup Complete! You can now run or build the Zatnum Scraper.
pause
