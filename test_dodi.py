import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

print("Fetching https://dodi-repacks.site/...")
try:
    r = requests.get('https://dodi-repacks.site/', headers=headers, timeout=10)
    print("Status code:", r.status_code)
    print("Content length:", len(r.text))
    print("Snippet:", repr(r.text[:500]))
    
    soup = BeautifulSoup(r.text, 'html.parser')
    articles = soup.select('article')
    print("Found articles count:", len(articles))
    
    h2_links = soup.select('h2.entry-title a, h1.entry-title a, h2 a')
    print("Found title links count:", len(h2_links))
    if h2_links:
        for a in h2_links[:5]:
            print(" Link:", a.get('href'), "| Text:", a.get_text(strip=True))

    print("\nFetching https://dodi-repacks.site/wp-sitemap.xml...")
    r_sm = requests.get('https://dodi-repacks.site/wp-sitemap.xml', headers=headers, timeout=10)
    print("Sitemap status:", r_sm.status_code)
    print("Sitemap snippet:", repr(r_sm.text[:500]))

except Exception as e:
    print("Error:", e)
