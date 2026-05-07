import sqlite3
import json
import time
from playwright.sync_api import sync_playwright

BASE_URL = "https://prosettings.net/players/"


# =========================================================
# DATABASE
# =========================================================

def init_db():

    conn = sqlite3.connect("esports.db")

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Nodes (
            NodeID INTEGER PRIMARY KEY AUTOINCREMENT,
            NodeType TEXT NOT NULL,
            Name TEXT NOT NULL,
            Attributes TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Edges (
            EdgeID INTEGER PRIMARY KEY AUTOINCREMENT,
            SourceNodeID INTEGER,
            TargetNodeID INTEGER,
            EdgeType TEXT,
            Metadata TEXT,
            FOREIGN KEY(SourceNodeID) REFERENCES Nodes(NodeID),
            FOREIGN KEY(TargetNodeID) REFERENCES Nodes(NodeID)
        )
    """)

    conn.commit()
    conn.close()

    print("Database initialized.")


def get_db_connection():

    conn = sqlite3.connect("esports.db")

    conn.row_factory = sqlite3.Row

    return conn


# =========================================================
# SCRAPER
# =========================================================

def scrape_players():

    init_db()

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=False)

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        page = context.new_page()

        # =========================================================
        # COLLECT PLAYER URLS
        # =========================================================

        urls = set()

        for page_num in range(1, 117):

            if page_num == 1:
                url = BASE_URL
            else:
                url = f"{BASE_URL}page/{page_num}/"

            print(f"\nScraping list page {page_num}")

            try:

                page.goto(url, wait_until="domcontentloaded", timeout=60000)

                time.sleep(0.7)

                links = page.locator('a[href*="/players/"]').all()

                for el in links:

                    href = el.get_attribute("href")

                    if not href:
                        continue

                    clean_url = href.rstrip("/")

                    # ---------------- SKIP PAGINATION LINKS ----------------

                    if "/page/" in clean_url:
                        continue

                    if clean_url.endswith("/players"):
                        continue

                    # remove fragments like #cs2
                    clean_url = clean_url.split("#")[0]

                    urls.add(clean_url)

            except Exception as e:

                print(f"Error on page {page_num}: {e}")

        print(f"\nCollected {len(urls)} UNIQUE player URLs.")

        # =========================================================
        # DATABASE CONNECTION
        # =========================================================

        conn = get_db_connection()

        processed = 0

        # =========================================================
        # PLAYER PAGE SCRAPING
        # =========================================================

        for url in urls:

            try:

                print(f"\nOpening: {url}")

                page.goto(url, wait_until="commit", timeout=15000)
                page.wait_for_selector("h1", timeout=5000)

                time.sleep(1)

                # =========================================================
                # USERNAME
                # =========================================================

                try:
                    username = page.locator("h1").inner_text().strip()
                except:
                    username = "Unknown"

                # =========================================================
                # TABLE DATA HELPER
                # =========================================================

                def get_table_data(label):

                    try:

                        row = page.locator(f"tr:has-text('{label}')")

                        value = row.locator("td").nth(1).inner_text().strip()

                        if value == "":
                            return "Unknown"

                        return value

                    except:
                        return "Unknown"

                # =========================================================
                # PLAYER DATA
                # =========================================================

                actual_name = get_table_data("Name")
                team_name = get_table_data("Team")
                country = get_table_data("Country")
                birthday = get_table_data("Birthday")

                if not team_name or team_name == "Unknown":
                    team_name = "Free Agent"

                print(f"SUCCESS: {username} | Team: {team_name}")

                # =========================================================
                # PLAYER ATTRIBUTES
                # =========================================================

                player_attributes = json.dumps({
                    "full_name": actual_name,
                    "country": country,
                    "birthday": birthday,
                    "profile_url": url
                })

                # =========================================================
                # DUPLICATE PREVENTION - PLAYER
                # =========================================================

                player_row = conn.execute("""
                    SELECT NodeID
                    FROM Nodes
                    WHERE Name = ?
                    AND NodeType = 'Player'
                """, (username,)).fetchone()

                if player_row:

                    player_id = player_row["NodeID"]

                    conn.execute("""
                        UPDATE Nodes
                        SET Attributes = ?
                        WHERE NodeID = ?
                    """, (player_attributes, player_id))

                else:

                    cursor = conn.execute("""
                        INSERT INTO Nodes (NodeType, Name, Attributes)
                        VALUES (?, ?, ?)
                    """, ("Player", username, player_attributes))

                    player_id = cursor.lastrowid

                # =========================================================
                # DUPLICATE PREVENTION - TEAM
                # =========================================================

                team_row = conn.execute("""
                    SELECT NodeID
                    FROM Nodes
                    WHERE Name = ?
                    AND NodeType = 'Team'
                """, (team_name,)).fetchone()

                if team_row:

                    team_id = team_row["NodeID"]

                else:

                    cursor = conn.execute("""
                        INSERT INTO Nodes (NodeType, Name, Attributes)
                        VALUES (?, ?, ?)
                    """, (
                        "Team",
                        team_name,
                        json.dumps({
                            "type": "organization"
                        })
                    ))

                    team_id = cursor.lastrowid

                # =========================================================
                # DUPLICATE PREVENTION - EDGE
                # =========================================================

                edge_row = conn.execute("""
                    SELECT EdgeID
                    FROM Edges
                    WHERE SourceNodeID = ?
                    AND TargetNodeID = ?
                    AND EdgeType = 'Plays_For'
                """, (
                    player_id,
                    team_id
                )).fetchone()

                if not edge_row:

                    conn.execute("""
                        INSERT INTO Edges
                        (SourceNodeID, TargetNodeID, EdgeType)
                        VALUES (?, ?, ?)
                    """, (
                        player_id,
                        team_id,
                        "Plays_For"
                    ))

                conn.commit()

                processed += 1

            except Exception as e:

                print(f"Error scraping {url}")
                print(e)

                continue

        conn.close()

        browser.close()

        print(f"\nDONE. Processed {processed} players.")


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    scrape_players()