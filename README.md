# Zatnum Scraper

Zatnum Scraper is a robust, free, and open-source B2B Lead Generation tool that extracts local business data from Google Maps. It is designed to be highly resilient against Google Maps UI updates and handles data deduplication automatically.

## Features

- **Automated Data Extraction:** Scrapes Business Name, Rating, Address, Website, and Phone Number from Google Maps.
- **Modern UI:** A sleek, responsive, dark-mode desktop interface built with `customtkinter`.
- **Zero UI Freezes:** Runs Playwright headless automation in a background daemon thread, allowing real-time logging without freezing the app.
- **Built-in Deduplication:** Uses O(1) hashing to ensure no duplicate phone numbers are saved to your CSV file.
- **Data Sanitation:** Automatically strips out Google font icons and hidden line breaks for clean, export-ready data.
- **Atomic Saving:** Saves leads in batches incrementally so you never lose data, even if the app is abruptly closed.

## Technologies Used

- **Python**
- **CustomTkinter:** For the graphical user interface.
- **Playwright (`sync_api`):** For dynamic headless browser rendering and Javascript evaluation.
- **Native CSV Module:** For ultra-lightweight, atomic data storage.

## Installation for Developers

1. Clone this repository.
2. Install the Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Install the Playwright Chromium browser binary:
   ```bash
   python -m playwright install chromium
   ```
   *(Or simply double-click the included `install_browser.bat` script on Windows!)*
4. Run the scraper:
   ```bash
   python main.py
   ```

## Installation for Non-Technical Users (Standalone `.exe`)

If you have downloaded the standalone release:
1. Extract the folder.
2. Double-click the **`install_browser.bat`** file **once** to download the background browser.
3. Open the `dist/Zatnum_Scraper` folder and double-click `Zatnum_Scraper.exe`.
4. Enter your Niche (e.g., "Plumbers") and Location (e.g., "Austin, TX") and click Start!

## Compiling to an Executable

If you want to package this script into your own `.exe` file, use PyInstaller. The codebase contains a built-in architecture hack to fix Playwright browser paths when bundled.

```bash
python -m PyInstaller --noconfirm --onedir --windowed --hidden-import "customtkinter" --name "Zatnum_Scraper" main.py
```

## Disclaimer
This project is for educational purposes only. Ensure you comply with Google's Terms of Service when scraping public data.

## License

[MIT](https://choosealicense.com/licenses/mit/)
