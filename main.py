import os
import sys

# CRITICAL: Playwright PyInstaller Gotcha Fix
# Must be set before importing playwright so that the compiled .exe
# looks for the Chromium browser in the standard user path instead of the temp _MEI folder.
# We ONLY apply this if running as a bundled PyInstaller executable.
if getattr(sys, 'frozen', False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

import threading
import queue
import time
import customtkinter as ctk
import csv
from playwright.sync_api import sync_playwright

# --- Configuration ---
CSV_FILE_PATH = "leads.csv"

# --- Helper Functions ---
def save_atomically(new_records, file_path):
    """Saves records atomically by writing to a temporary file and renaming it."""
    if not new_records:
        return
    
    fieldnames = ["Name", "Rating", "Address", "Website", "Phone", "URL"]
    existing_records = []
    
    if os.path.exists(file_path):
        try:
            with open(file_path, mode='r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_records.append(row)
        except Exception:
            pass
            
    combined_records = existing_records + new_records
    temp_path = file_path + ".tmp"
    try:
        with open(temp_path, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(combined_records)
        # Atomically replace the old file with the new file
        os.replace(temp_path, file_path)
    except Exception as e:
        raise Exception(f"Failed to save data atomically: {e}")

# --- Scraper Worker (Runs in Background Thread) ---
def run_scraper(niche, location, headless, log_queue):
    query = f"{niche} in {location}"
    log_queue.put(f"--- Starting Scraper for: '{query}' ---")
    log_queue.put(f"Headless Mode: {'ON' if headless else 'OFF'}")
    
    try:
        with sync_playwright() as p:
            log_queue.put("Launching browser...")
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page()
            
            # 1. Navigate directly to the Search URL
            import urllib.parse
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://www.google.com/maps/search/{encoded_query}"
            
            log_queue.put(f"Navigating directly to search results...")
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            log_queue.put("Waiting for results feed to load...")
            
            # 2. Wait for results feed
            try:
                page.wait_for_selector('a[href*="https://www.google.com/maps/place/"]', timeout=20000)
            except Exception:
                log_queue.put("WARNING: No results found or timeout while waiting for results.")
                browser.close()
                log_queue.put("DONE")
                return

            log_queue.put("Scrolling down to load all results. This may take a moment...")
            
            # 3. Scroll to load all places in the side panel
            places_hrefs = set()
            previous_count = 0
            retries = 0
            
            while True:
                links = page.query_selector_all('a[href*="https://www.google.com/maps/place/"]')
                for link in links:
                    try:
                        href = link.get_attribute('href')
                        if href:
                            places_hrefs.add(href)
                    except Exception:
                        pass
                
                current_count = len(places_hrefs)
                if current_count == previous_count:
                    retries += 1
                    time.sleep(2)
                    if retries >= 3: # If count hasn't changed after a few attempts, we're at the bottom
                        break
                else:
                    retries = 0 # reset retries if we found new items
                    log_queue.put(f"Loaded {current_count} results so far...")
                
                previous_count = current_count
                
                # Evaluate JS to scroll the feed container to the bottom
                try:
                    page.evaluate('''() => {
                        const feed = document.querySelector('div[role="feed"]');
                        if (feed) {
                            feed.scrollTop = feed.scrollHeight;
                        } else {
                            window.scrollBy(0, 5000);
                        }
                    }''')
                except Exception:
                    pass
                time.sleep(1.5)
            
            places_list = list(places_hrefs)
            log_queue.put(f"Total businesses discovered: {len(places_list)}. Beginning extraction...")
            
            # 4. Data Deduplication setup
            existing_phones = set()
            if os.path.exists(CSV_FILE_PATH):
                try:
                    with open(CSV_FILE_PATH, mode='r', encoding='utf-8', newline='') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if 'Phone' in row and row['Phone']:
                                existing_phones.add(str(row['Phone']))
                    log_queue.put(f"Loaded {len(existing_phones)} existing phone numbers from database.")
                except Exception as e:
                    log_queue.put(f"Warning: Could not read existing database: {e}")
            
            new_leads = []
            
            # 5. Extract data from each place
            for index, url in enumerate(places_list):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(1.5) # Allow dynamic content to stabilize
                    
                    name, address, website, phone, rating = "N/A", "N/A", "N/A", "N/A", "N/A"
                    
                    try:
                        name_elem = page.query_selector('h1')
                        if name_elem:
                            name = name_elem.inner_text().strip()
                    except Exception: pass
                    
                    try:
                        rating_elem = page.query_selector('div.fontBodyMedium > span[role="img"]')
                        if rating_elem:
                            rating = rating_elem.get_attribute('aria-label')
                    except Exception: pass
                    
                    try:
                        address_btn = page.query_selector('button[data-item-id="address"]')
                        if address_btn:
                            raw_address = address_btn.inner_text()
                            # Clean address: remove Google icons (, ) and replace newlines with space
                            clean_address = raw_address.replace('', '').replace('', '').replace('\n', ' ').strip()
                            address = clean_address
                    except Exception: pass
                    
                    try:
                        website_a = page.query_selector('a[data-item-id="authority"]')
                        if website_a:
                            website = website_a.get_attribute('href')
                    except Exception: pass
                    
                    try:
                        phone_btn = page.query_selector('button[data-item-id*="phone:tel:"]')
                        if phone_btn:
                            raw_phone = phone_btn.inner_text()
                            # Clean phone: remove Google icons and remove all newlines
                            clean_phone = raw_phone.replace('', '').replace('', '').replace('\n', '').strip()
                            phone = clean_phone
                    except Exception: pass
                    
                    if phone != "N/A" and phone in existing_phones:
                        log_queue.put(f"[{index+1}/{len(places_list)}] SKIPPED (Duplicate Phone): {name}")
                        continue
                        
                    if phone != "N/A":
                        existing_phones.add(phone)
                        
                    new_leads.append({
                        "Name": name,
                        "Rating": rating,
                        "Address": address,
                        "Website": website,
                        "Phone": phone,
                        "URL": url
                    })
                    
                    log_queue.put(f"[{index+1}/{len(places_list)}] SCRAPED: {name} | Phone: {phone}")
                    
                    # Atomic batch save every 5 records to avoid data loss on crash
                    if len(new_leads) >= 5:
                        save_atomically(new_leads, CSV_FILE_PATH)
                        new_leads = [] # Reset after saving
                        
                except Exception as e:
                    log_queue.put(f"[{index+1}/{len(places_list)}] ERROR scraping business: {e}")
                    continue
            
            # Final save for any remaining leads
            if new_leads:
                save_atomically(new_leads, CSV_FILE_PATH)
                
            browser.close()
            log_queue.put("--- Scraping Completed Successfully ---")
            log_queue.put("DONE")
            
    except Exception as e:
        log_queue.put(f"CRITICAL ERROR: {e}")
        log_queue.put("DONE_ERROR")

# --- UI Application (Main Thread) ---
class ZatnumScraperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Setup Window
        self.title("Zatnum Scraper - B2B Lead Generator")
        self.geometry("700x550")
        self.resizable(False, False)
        
        # Appearance
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        # Queue for thread-safe logging
        self.log_queue = queue.Queue()
        
        self.build_ui()
        self.check_queue()
        
    def build_ui(self):
        # Header
        self.header_label = ctk.CTkLabel(self, text="Zatnum Scraper", font=ctk.CTkFont(size=24, weight="bold"))
        self.header_label.pack(pady=(20, 10))
        
        self.sub_label = ctk.CTkLabel(self, text="Automated Google Maps B2B Lead Generation", text_color="gray")
        self.sub_label.pack(pady=(0, 20))
        
        # Input Frame
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.pack(pady=10, padx=20, fill="x")
        
        # Niche Input
        self.niche_label = ctk.CTkLabel(self.input_frame, text="Niche (e.g. Plumbers):")
        self.niche_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.niche_entry = ctk.CTkEntry(self.input_frame, width=200)
        self.niche_entry.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        # Location Input
        self.location_label = ctk.CTkLabel(self.input_frame, text="Location (e.g. Austin, TX):")
        self.location_label.grid(row=0, column=2, padx=10, pady=10, sticky="w")
        self.location_entry = ctk.CTkEntry(self.input_frame, width=200)
        self.location_entry.grid(row=0, column=3, padx=10, pady=10, sticky="w")
        
        # Options Frame
        self.options_frame = ctk.CTkFrame(self)
        self.options_frame.pack(pady=10, padx=20, fill="x")
        
        # Headless Checkbox
        self.headless_var = ctk.BooleanVar(value=True)
        self.headless_checkbox = ctk.CTkCheckBox(self.options_frame, text="Run in Background (Headless)", variable=self.headless_var)
        self.headless_checkbox.pack(side="left", padx=10, pady=10)
        
        # Start Button
        self.start_btn = ctk.CTkButton(self.options_frame, text="START SCRAPING", font=ctk.CTkFont(weight="bold"), fg_color="#28a745", hover_color="#218838", command=self.start_scraping)
        self.start_btn.pack(side="right", padx=10, pady=10)
        
        # Terminal / Log Output
        self.log_label = ctk.CTkLabel(self, text="Execution Logs:")
        self.log_label.pack(anchor="w", padx=20, pady=(10, 0))
        
        self.log_box = ctk.CTkTextbox(self, state="disabled", fg_color="#1e1e1e", text_color="#00ff00", font=("Consolas", 12))
        self.log_box.pack(pady=(0, 20), padx=20, fill="both", expand=True)

    def insert_log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def start_scraping(self):
        niche = self.niche_entry.get().strip()
        location = self.location_entry.get().strip()
        
        if not niche or not location:
            self.insert_log("ERROR: Please enter both Niche and Location.")
            return
            
        # Disable button during execution
        self.start_btn.configure(state="disabled", fg_color="gray")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end") # Clear logs
        self.log_box.configure(state="disabled")
        
        headless = self.headless_var.get()
        
        # Start background daemon thread
        threading.Thread(
            target=run_scraper,
            args=(niche, location, headless, self.log_queue),
            daemon=True
        ).start()

    def check_queue(self):
        """Polls the queue for messages from the background scraping thread."""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if msg == "DONE" or msg == "DONE_ERROR":
                    # Re-enable the button when scraping is finished or errored
                    self.start_btn.configure(state="normal", fg_color="#28a745")
                else:
                    self.insert_log(msg)
        except queue.Empty:
            pass
        
        # Schedule the next poll in 100 milliseconds
        self.after(100, self.check_queue)

if __name__ == "__main__":
    app = ZatnumScraperApp()
    app.mainloop()