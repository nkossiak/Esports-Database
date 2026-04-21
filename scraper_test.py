import sqlite3
import json
import time
from playwright.sync_api import sync_playwright

TARGET_URL = "https://prosettings.net/players/"

def init_db():
    conn = sqlite3.connect('esports.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Nodes (
            NodeID INTEGER PRIMARY KEY AUTOINCREMENT,
            NodeType TEXT NOT NULL,
            Name TEXT NOT NULL,
            Attributes TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Edges (
            EdgeID INTEGER PRIMARY KEY AUTOINCREMENT,
            SourceNodeID INTEGER,
            TargetNodeID INTEGER,
            EdgeType TEXT,
            Metadata TEXT,
            FOREIGN KEY(SourceNodeID) REFERENCES Nodes(NodeID),
            FOREIGN KEY(TargetNodeID) REFERENCES Nodes(NodeID)
        )
    ''')
    conn.commit()
    conn.close()
    print("Database tables initialized.")

def get_db_connection():
    conn = sqlite3.connect('esports.db')
    conn.row_factory = sqlite3.Row
    return conn

def scrape_deep_details():
    init_db()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        page = context.new_page()
        
        print(f"Connecting to {TARGET_URL}...")
        page.goto(TARGET_URL, wait_until="domcontentloaded")
        time.sleep(6) 

        player_links = page.locator('a[href*="/players/"]').all()
        urls = []
        for el in player_links:
            url = el.get_attribute("href")
            if url and "/players/" in url:
                clean_url = url.rstrip('/')
                slug = clean_url.split('/')[-1]
                if slug not in ['players', ''] and url not in urls:
                    urls.append(url)

        print(f"Found {len(urls)} player profiles. Starting Deep Scrape...")

        conn = get_db_connection()
        count = 0

        for url in urls:
            try:
                print(f"\nNavigating to: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(4) 

                username = page.locator("h1").inner_text().strip()

                def get_table_data(label):
                    try:
                        # Grab all text in the row to find the data cell
                        row_text = page.locator(f"tr:has-text('{label}') >> td").all_inner_texts()
                        if not row_text: return "Unknown"
                        
                        val = row_text[-1].strip()
                        
                        # CLEANUP LOGIC:
                        # 1. Avoid "Always" bug (from "Always use..." tooltips)
                        if val.lower() == "always":
                            # Try to get the cell content specifically by excluding hidden elements
                            val = page.locator(f"tr:has-text('{label}') >> td").last.evaluate("node => node.innerText").strip()
                        
                        # 2. Avoid "Team Color" bug
                        if "Team Color" in val:
                            return "Free Agent" # Or try to find the text node specifically
                            
                        return val if val else "Unknown"
                    except:
                        return "Unknown"

                actual_name = get_table_data("Name")
                team_name = get_table_data("Team")
                country = get_table_data("Country")
                birthday = get_table_data("Birthday")

                # One last safety check on names
                if actual_name == "Always" or "Twitter" in actual_name:
                    actual_name = "Unknown"

                print(f"SUCCESS: {username} | Real Name: {actual_name} | Team: {team_name}")

                # --- Database Logic ---
                attributes = json.dumps({
                    "full_name": actual_name,
                    "birthday": birthday,
                    "country": country,
                    "profile_url": url
                })

                cursor = conn.execute(
                    'INSERT INTO Nodes (NodeType, Name, Attributes) VALUES (?, ?, ?)',
                    ('Player', username, attributes)
                )
                player_id = cursor.lastrowid

                team_row = conn.execute('SELECT NodeID FROM Nodes WHERE Name = ? AND NodeType = "Team"', (team_name,)).fetchone()
                if not team_row:
                    cursor = conn.execute('INSERT INTO Nodes (NodeType, Name, Attributes) VALUES (?, ?, ?)',
                                         ('Team', team_name, json.dumps({'type': 'organization'})))
                    team_id = cursor.lastrowid
                else:
                    team_id = team_row['NodeID']

                conn.execute('INSERT INTO Edges (SourceNodeID, TargetNodeID, EdgeType) VALUES (?, ?, ?)',
                             (player_id, team_id, 'Plays_For'))

                count += 1
                if count >= 20: break # Increased to 20 for your final run!
                
            except Exception as e:
                print(f"Error on {url}: {e}")
                continue

        conn.commit()
        conn.close()
        browser.close()
        print(f"\nDone! Added {count} players with deep attributes.")

if __name__ == "__main__":
    scrape_deep_details()