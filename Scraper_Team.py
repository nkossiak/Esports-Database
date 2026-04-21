import sqlite3
import json
import time
import requests
import re
from bs4 import BeautifulSoup

# Configuration
DB_PATH = 'esports.db'
HEADERS = {
    'User-Agent': 'EsportsDatabaseProject/1.0 (Contact: yourname@email.com) Educational Research'
}

def get_wiki_info(team_name):
    """Scrapes Wikipedia with fallback for (esports) naming conventions."""
    
    # Try primary name first, then fall back to (esports)
    name_variations = [
        team_name.replace(' ', '_'),
        f"{team_name.replace(' ', '_')}_(esports)"
    ]
    
    for variant in name_variations:
        url = f"https://en.wikipedia.org/wiki/{variant}"
        try:
            # Respectful delay between variations if the first fails
            response = requests.get(url, headers=HEADERS, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                infobox = soup.find("table", {"class": "infobox"})
                
                if infobox:
                    scraped_data = {}
                    rows = infobox.find_all("tr")
                    
                    for row in rows:
                        th = row.find("th")
                        td = row.find("td")
                        
                        if th and td:
                            label = th.get_text(strip=True).lower()
                            value = td.get_text(separator=" ", strip=True).split('[')[0].strip()
                            
                            # Extract Founded Year
                            if "founded" in label and 'founded' not in scraped_data:
                                year_match = re.search(r'\d{4}', value)
                                scraped_data['founded'] = year_match.group(0) if year_match else value
                            
                            # Extract Location
                            if ("location" in label or "headquarters" in label) and 'location' not in scraped_data:
                                scraped_data['location'] = value
                                
                    if scraped_data:
                        print(f"Found info for {team_name} at: {url}")
                        return scraped_data
            
            # If 404, loop to the next variation (e.g., Sentinels (esports))
            time.sleep(0.5) 

        except Exception as e:
            print(f"Error checking {variant}: {e}")
            
    return None

def run_smart_update():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query teams that are missing data and haven't been successfully checked recently
    cursor.execute('''
        SELECT NodeID, Name, Attributes 
        FROM Nodes 
        WHERE NodeType = "Team" 
        AND (Attributes NOT LIKE '%"location"%' OR Attributes NOT LIKE '%"founded"%')
    ''')
    
    teams_to_update = cursor.fetchall()
    
    if not teams_to_update:
        print("All teams are up to date.")
        return

    for team in teams_to_update:
        name = team['Name']
        try:
            attrs = json.loads(team['Attributes']) if team['Attributes'] else {}
        except:
            attrs = {}

        # Respectful delay between different teams
        time.sleep(1.5) 

        print(f"Checking Wikipedia for: {name}...")
        new_info = get_wiki_info(name)

        if new_info:
            attrs.update(new_info)
            cursor.execute(
                'UPDATE Nodes SET Attributes = ? WHERE NodeID = ?',
                (json.dumps(attrs), team['NodeID'])
            )
            conn.commit()
            print(f"✅ Updated {name}")
        else:
            # Mark as attempted so we don't hit the same name repeatedly
            attrs['wiki_found'] = False
            cursor.execute(
                'UPDATE Nodes SET Attributes = ? WHERE NodeID = ?',
                (json.dumps(attrs), team['NodeID'])
            )
            conn.commit()
            print(f"❌ No info found for {name} (even with (esports) suffix)")

    conn.close()

if __name__ == "__main__":
    run_smart_update()