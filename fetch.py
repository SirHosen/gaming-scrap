import urllib.request
import re

# Fetch homepage to find a game link
req = urllib.request.Request("https://switchroms.io/", headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    # Find a game link
    links = re.findall(r'href="(https://switchroms\.io/[a-z0-9-]+/)"', html)
    if links:
        game_url = links[2] # Pick one
        print("Selected URL:", game_url)
        
        # Fetch game page
        req_game = urllib.request.Request(game_url, headers={'User-Agent': 'Mozilla/5.0'})
        game_html = urllib.request.urlopen(req_game).read().decode('utf-8')
        
        with open('page.html', 'w', encoding='utf-8') as f:
            f.write(game_html)
        print("Saved to page.html")
    else:
        print("No game link found")
except Exception as e:
    print("Error:", e)
