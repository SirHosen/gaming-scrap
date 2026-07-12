import os
import csv
import json
import time
import ctypes
import requests
from urllib.parse import urljoin, quote_plus
from bs4 import BeautifulSoup

# --- COLOR SYSTEM & WINDOWS CMD CONFIG ---
# Enable Virtual Terminal Processing on Windows to support ANSI color escape sequences
if os.name == 'nt':
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

class Colors:
    GREEN = '\033[92m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    WHITE = '\033[97m'
    GREY = '\033[90m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# --- CONFIGURATION & HEADERS ---
BASE_URL = "https://switchroms.io/"
DELAY = 1.0  # Safe delay (seconds) between requests to respect the target server

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://switchroms.io/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

# Initialize HTTP Session to preserve cookies across redirect pages
session = requests.Session()
session.headers.update(HEADERS)

def safe_request(url, retries=3):
    """
    Performs HTTP request with automatic retries, timeout management,
    and respectful rate-limiting (delay).
    """
    time.sleep(DELAY)
    for attempt in range(retries):
        try:
            response = session.get(url, timeout=15)
            if response.status_code == 200:
                return response.text
            elif response.status_code == 403:
                print(f"  {Colors.RED}[!] HTTP 403 Forbidden. Retrying in 3 seconds...{Colors.RESET}")
                time.sleep(3)
            else:
                print(f"  {Colors.YELLOW}[!] Bad Status Code ({response.status_code}) on attempt {attempt+1}/{retries}.{Colors.RESET}")
        except requests.RequestException as e:
            print(f"  {Colors.YELLOW}[!] Attempt {attempt+1}/{retries} failed: {e}{Colors.RESET}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
    return None

# --- PARSING & SCRAPING ENGINE ---

def get_page_url(page_num, search_query=None):
    """Generates paginated URLs matching WordPress-style search or archive paths."""
    if search_query:
        encoded_query = quote_plus(search_query)
        if page_num == 1:
            return f"{BASE_URL}?s={encoded_query}"
        else:
            return f"{BASE_URL}page/{page_num}/?s={encoded_query}"
    else:
        if page_num == 1:
            return BASE_URL
        else:
            return f"{BASE_URL}page/{page_num}/"

def extract_final_download_url(redirect_url):
    """
    Lapis 3: Fetches the final file-host URL from a mirror redirect page (?download=X).
    """
    html = safe_request(redirect_url)
    if not html:
        return "N/A"
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Strategy A: Retrieve download link from active button container
    link_element = soup.select_one('#download-active a')
    if not link_element:
        # Strategy B: Fallback to fallback text paragraph "click here"
        link_element = soup.select_one('.aligncenter.mt-2 a')
        
    if link_element and link_element.get('href'):
        return link_element.get('href')
        
    return "N/A"

def parse_download_mirrors(detail_url, format_filter=None, hoster_filter=None):
    """
    Lapis 2: Retrieves download mirror list from game detail page.
    Filters mirror buttons before requesting final URLs to optimize speed.
    """
    download_page_url = detail_url.rstrip('/') + "/?download"
    print(f"  -> Scraping mirror index: {Colors.GREY}{download_page_url}{Colors.RESET}")
    
    html = safe_request(download_page_url)
    if not html:
        return []
        
    soup = BeautifulSoup(html, 'html.parser')
    mirrors = []
    
    # Locate all download mirror items matching .a-link-button
    link_buttons = soup.select('a.a-link-button')
    for link in link_buttons:
        if not link.get('href'):
            continue
            
        redirect_url = urljoin(BASE_URL, link.get('href'))
        
        # Extract title string (e.g., "NSP ROM | 3.51 GB | Megaup")
        title_span = link.select_one('.link-title')
        raw_text = title_span.text.strip() if title_span else "Unknown Mirror"
        
        # Split mirror metadata
        parts = [p.strip() for p in raw_text.split('|')]
        rom_format = parts[0] if len(parts) > 0 else "N/A"
        size = parts[1] if len(parts) > 1 else "N/A"
        hoster_name = parts[2] if len(parts) > 2 else "Unknown"
        
        # --- PRE-FILTERING OPTIMIZATION ---
        # Skip requesting redirect pages of mirrors that don't match the selected filters.
        if format_filter and format_filter != "ALL":
            # Check format match (e.g. NSP, XCI, UPDATE, DLC)
            if format_filter not in rom_format.upper():
                continue
                
        if hoster_filter and hoster_filter != "ALL":
            # Check hoster match (e.g. MEDIAFIRE, MEGAUP, 1FICHIER)
            if hoster_filter not in hoster_name.upper():
                continue
        
        print(f"     {Colors.GREEN}✔{Colors.RESET} Fetching link: {Colors.CYAN}{hoster_name}{Colors.RESET} ({rom_format})")
        # Step into Lapis 3 to get final host link
        final_link = extract_final_url = extract_final_download_url(redirect_url)
        
        mirrors.append({
            "raw_text": raw_text,
            "format": rom_format,
            "size": size,
            "hoster": hoster_name,
            "redirect_url": redirect_url,
            "final_link": final_link
        })
        
    return mirrors

def run_scraper(search_query=None, max_pages=1, format_filter=None, hoster_filter=None):
    """
    Lapis 1: Sweeps the pages of games (latest or search query), parses card list, 
    and iterates detail pages.
    """
    start_time = time.time()
    all_games = []
    
    print(f"\n{Colors.CYAN}--- Starting scraping session ---{Colors.RESET}")
    
    for page in range(1, max_pages + 1):
        target_url = get_page_url(page, search_query)
        print(f"\n{Colors.BOLD}[PAGE {page}/{max_pages}]{Colors.RESET} Fetching: {Colors.GREY}{target_url}{Colors.RESET}")
        
        html = safe_request(target_url)
        if not html:
            print(f"  {Colors.RED}[!] Could not retrieve page {page}. Skipping.{Colors.RESET}")
            continue
            
        soup = BeautifulSoup(html, 'html.parser')
        post_items = soup.select('.list-post .post-item')
        
        if not post_items:
            print(f"  {Colors.YELLOW}[!] No games found on page {page}. Ending page sweep.{Colors.RESET}")
            break
            
        print(f"  {Colors.GREEN}✔{Colors.RESET} Found {len(post_items)} games on page {page}.")
        
        for idx, item in enumerate(post_items, 1):
            # Extract detail anchor link
            link_tag = item.select_one('a.wrapper-item-title')
            if not link_tag or not link_tag.get('href'):
                continue
                
            detail_url = link_tag.get('href')
            
            # Extract game title
            title_tag = item.select_one('.title-post')
            title = title_tag.text.strip() if title_tag else "No Title"
            
            # Extract card spans metadata
            meta_spans = item.select('.text-cat.version')
            meta_size = "N/A"
            meta_genre = "N/A"
            
            if len(meta_spans) > 0:
                meta_size = meta_spans[0].text.strip()
            if len(meta_spans) > 1:
                meta_genre = meta_spans[1].text.strip()
                
            print(f"\n  [{idx}] Processing: {Colors.BOLD}{Colors.WHITE}{title}{Colors.RESET}")
            print(f"      Size/Ver: {Colors.YELLOW}{meta_size}{Colors.RESET} | Genre/Pub: {Colors.YELLOW}{meta_genre}{Colors.RESET}")
            
            # Fetch details & download links
            mirrors = parse_download_mirrors(detail_url, format_filter, hoster_filter)
            
            # Only save game if at least one mirror survived the filter
            if mirrors:
                all_games.append({
                    "title": title,
                    "meta_size": meta_size,
                    "meta_genre": meta_genre,
                    "detail_url": detail_url,
                    "mirrors": mirrors
                })
            else:
                print(f"      {Colors.YELLOW}ℹ No mirrors matched filters for this game.{Colors.RESET}")
                
    elapsed_time = time.time() - start_time
    return all_games, elapsed_time

# --- DATA EXPORTERS ---

def save_output(data, save_format):
    """Exports data cleanly based on user preference (CSV, JSON, or Both)."""
    json_path = "switch_games.json"
    csv_path = "switch_games.csv"
    
    if save_format in ["2", "3"]:
        # Export JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"  {Colors.GREEN}✔{Colors.RESET} Successfully saved JSON database: {Colors.UNDERLINE}{json_path}{Colors.RESET}")
        
    if save_format in ["1", "3"]:
        # Export CSV
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Game Title", 
                "Size/Version Info", 
                "Genre/Publisher Info", 
                "Detail Page URL", 
                "ROM Format", 
                "File Size", 
                "Hosting Service", 
                "Redirect URL", 
                "Direct Download URL"
            ])
            
            for game in data:
                for mirror in game["mirrors"]:
                    writer.writerow([
                        game["title"],
                        game["meta_size"],
                        game["meta_genre"],
                        game["detail_url"],
                        mirror["format"],
                        mirror["size"],
                        mirror["hoster"],
                        mirror["redirect_url"],
                        mirror["final_link"]
                    ])
        print(f"  {Colors.GREEN}✔{Colors.RESET} Successfully saved CSV spreadsheet: {Colors.UNDERLINE}{csv_path}{Colors.RESET}")

# --- TERMINAL VISUAL INTERFACES ---

def print_banner():
    banner = f"""{Colors.CYAN}{Colors.BOLD}
   ========================================================================
     ██████╗ ██╗    ██╗██╗████████╗ ██████╗██╗  ██╗██████╗  ██████╗ ███╗   ███╗███████╗
    ██╔════╝ ██║    ██║██║╚══██╔══╝██╔════╝██║  ██║██╔══██╗██╔═══██╗████╗ ████║██╔════╝
    ╚█████╗  ██║ █╗ ██║██║   ██║   ██║     ███████║██████╔╝██║   ██║██╔████╔██║███████╗
     ╚═══██╗ ██║███╗██║██║   ██║   ██║     ██╔══██║██╔══██╗██║   ██║██║╚██╔╝██║╚════██║
    ██████╔╝ ╚███╔███╔╝██║   ██║   ╚██████╗██║  ██║██║  ██║╚██████╔╝██║ ╚═╝ ██║███████║
    ╚═════╝   ╚══╝╚══╝ ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝
                            NINTENDO SWITCH ROMS SCRAPER v2.0
   ========================================================================{Colors.RESET}"""
    print(banner)

def print_summary(data, elapsed_time):
    print(f"\n{Colors.GREEN}{Colors.BOLD}=================== SCRAPING SUMMARY ==================={Colors.RESET}")
    print(f"Total Games Extracted  : {Colors.WHITE}{len(data)}{Colors.RESET}")
    print(f"Total Mirror Links     : {Colors.WHITE}{sum(len(g['mirrors']) for g in data)}{Colors.RESET}")
    print(f"Execution Duration     : {Colors.WHITE}{elapsed_time:.2f} seconds{Colors.RESET}")
    print(f"Average Speed          : {Colors.WHITE}{elapsed_time/max(1, len(data)):.2f} sec/game{Colors.RESET}")
    print(f"{Colors.GREEN}========================================================{Colors.RESET}\n")

def get_input_choices():
    """Gathers user choice configurations in interactive menu."""
    # 1. Action mode
    print(f"{Colors.BOLD}1. Select Action Mode:{Colors.RESET}")
    print("  [1] Scrape latest games (Homepage)")
    print("  [2] Search specific games by keyword")
    mode = input("Select option (default: 1): ").strip()
    if mode not in ["1", "2"]:
        mode = "1"
        
    search_q = None
    if mode == "2":
        search_q = input("\nEnter game search keywords (e.g. Zelda, Mario): ").strip()
        while not search_q:
            search_q = input("Search query cannot be empty: ").strip()
            
    # 2. Maximum pages
    print(f"\n{Colors.BOLD}2. How many pages to sweep?{Colors.RESET}")
    pages_input = input("Enter number of pages (default: 1): ").strip()
    max_p = int(pages_input) if pages_input.isdigit() and int(pages_input) > 0 else 1
    
    # 3. Format filtering
    print(f"\n{Colors.BOLD}3. Filter File Format:{Colors.RESET}")
    print("  [1] NSP (Standard Base Games)")
    print("  [2] XCI (Cartridge Dumps)")
    print("  [3] UPDATE (NSP Game Patches)")
    print("  [4] DLC (Add-on Contents)")
    print("  [5] ALL Formats")
    format_opt = input("Select format filter (default: 5): ").strip()
    format_map = {"1": "NSP ROM", "2": "XCI ROM", "3": "UPDATE", "4": "DLC", "5": "ALL"}
    format_filter = format_map.get(format_opt, "ALL")
    
    # 4. Hoster filtering
    print(f"\n{Colors.BOLD}4. Filter File Hosting Provider:{Colors.RESET}")
    print("  [1] Mediafire")
    print("  [2] MegaUp")
    print("  [3] 1fichier")
    print("  [4] Buzzheavier")
    print("  [5] Terabox")
    print("  [6] Send.cm")
    print("  [7] ALL Providers")
    hoster_opt = input("Select hoster filter (default: 7): ").strip()
    hoster_map = {
        "1": "MEDIAFIRE", "2": "MEGAUP", "3": "1FICHIER",
        "4": "BUZZHEAVIER", "5": "TERABOX", "6": "SEND.CM", "7": "ALL"
    }
    hoster_filter = hoster_map.get(hoster_opt, "ALL")
    
    # 5. Output file format
    print(f"\n{Colors.BOLD}5. Choose Output Format:{Colors.RESET}")
    print("  [1] Excel Spreadsheet (CSV)")
    print("  [2] Database File (JSON)")
    print("  [3] Both formats")
    save_format = input("Select output format (default: 3): ").strip()
    if save_format not in ["1", "2", "3"]:
        save_format = "3"
        
    return search_q, max_p, format_filter, hoster_filter, save_format

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print_banner()
    
    # Gather configuration variables from CLI menus
    search_q, max_p, format_f, hoster_f, save_f = get_input_choices()
    
    # Run the main engine
    scraped_games, elapsed = run_scraper(
        search_query=search_q, 
        max_pages=max_p, 
        format_filter=format_f, 
        hoster_filter=hoster_f
    )
    
    # Output the database
    if scraped_games:
        print(f"\n{Colors.CYAN}--- Exporting results ---{Colors.RESET}")
        save_output(scraped_games, save_f)
        print_summary(scraped_games, elapsed)
    else:
        print(f"\n{Colors.RED}[!] Scraping completed but no links matched your filters/search.{Colors.RESET}\n")
    
    print(f"{Colors.BOLD}{Colors.GREEN}[FINISHED]{Colors.RESET} System terminated successfully. Thank you for using SwitchRoms Scraper!")
