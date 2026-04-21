import sqlite3
import json
import time
import re
import os
from playwright.sync_api import sync_playwright

# Tiers to scrape
TARGET_URLS = [
    "https://liquipedia.net/valorant/S-Tier_Tournaments",
    "https://liquipedia.net/valorant/A-Tier_Tournaments"
]

def get_db_connection():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, 'esports.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def scrape_everything():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        conn = get_db_connection()
        cursor = conn.cursor()

        for main_url in TARGET_URLS:
            tier = "S-Tier" if "S-Tier" in main_url else "A-Tier"
            print(f"\n=== SCRAPING {tier} LIST ===")
            page.goto(main_url, wait_until="networkidle")
            time.sleep(2)

            rows = page.locator("tr").all()
            for row in rows:
                cells = row.locator("td").all()
                if len(cells) < 4: continue

                # Extract Tournament Name and Link
                name_cell = cells[1]
                name = name_cell.inner_text().split('\n')[0].strip()
                link_el = name_cell.locator("a").first
                
                if not any(k in name for k in ["VALORANT", "VCT", "Masters", "Champions", "Evolution", "Clash"]):
                    continue

                # Metadata Extraction
                texts = [c.inner_text().strip() for c in cells]
                prize = next((t for t in texts if "$" in t), "TBD")
                year_match = re.search(r'(202\d)', " ".join(texts))
                year = year_match.group(1) if year_match else "2026"
                
                # Location Logic
                location = "Online"
                pots = [texts[4] if len(texts)>4 else None, texts[3] if len(texts)>3 else None]
                for p_loc in pots:
                    if p_loc and "$" not in p_loc and year not in p_loc and len(p_loc) > 1:
                        location = p_loc.split('\n')[0].strip(); break

                print(f"\nProcessing: {name}")

                # Sync Tournament Node
                attr = json.dumps({"country": location, "year": year, "prize_pool": prize, "tier": tier})
                cursor.execute('INSERT OR IGNORE INTO Nodes (NodeType, Name, Attributes) VALUES ("Tournament", ?, ?)', (name, attr))
                cursor.execute('UPDATE Nodes SET Attributes = ? WHERE Name = ? AND NodeType = "Tournament"', (attr, name))
                t_id = conn.execute('SELECT NodeID FROM Nodes WHERE Name = ? AND NodeType = "Tournament"', (name,)).fetchone()[0]

                # --- PARTICIPANT DRILL DOWN ---
                if link_el.count() > 0:
                    tourney_url = "https://liquipedia.net" + link_el.get_attribute("href")
                    sub_page = context.new_page()
                    try:
                        sub_page.goto(tourney_url, wait_until="networkidle", timeout=30000)
                        
                        # Use the working selectors from your dry run
                        elements = sub_page.locator(".teamcard, .teamcard-inner").locator("b a").all()
                        if not elements:
                            elements = sub_page.locator(".team-template-text a").all()

                        found_teams = set()
                        for el in elements:
                            team_name = el.inner_text().strip()
                            # Filter noise and short abbreviations (C9, SEN, etc) to prevent duplicates
                            if not team_name or len(team_name) <= 3 or team_name in ["TBD", "TBA"]:
                                continue
                            
                            if team_name in found_teams: continue
                            found_teams.add(team_name)

                            # Sync Team and Edge
                            cursor.execute('INSERT OR IGNORE INTO Nodes (NodeType, Name, Attributes) VALUES ("Team", ?, ?)', 
                                         (team_name, json.dumps({'game': 'Valorant'})))
                            team_id = conn.execute('SELECT NodeID FROM Nodes WHERE Name = ? AND NodeType = "Team"', (team_name,)).fetchone()[0]
                            cursor.execute('INSERT OR IGNORE INTO Edges (SourceNodeID, TargetNodeID, EdgeType) VALUES (?, ?, "Played_In")', (t_id, team_id))
                        
                        print(f"  > Linked {len(found_teams)} teams.")
                        conn.commit()
                    except Exception as e:
                        print(f"  > Error on {name}: {e}")
                    finally:
                        sub_page.close()

        conn.close()
        browser.close()
        print("\nAll data synced. Your graph is now fully connected!")

if __name__ == "__main__":
    scrape_everything()