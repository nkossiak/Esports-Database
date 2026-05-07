import sqlite3
import json
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

        # -------------------------------------------------
        # BROWSER
        # -------------------------------------------------

        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0"
        )

        page = context.new_page()

        # -------------------------------------------------
        # BLOCK HEAVY RESOURCES
        # -------------------------------------------------

        page.route(
            "**/*",
            lambda route:
                route.abort()
                if route.request.resource_type in [
                    "image",
                    "media",
                    "font"
                ]
                else route.continue_()
        )

        # =========================================================
        # INFINITE SCROLL URL COLLECTION
        # =========================================================

        urls = set()

        page.goto(
            BASE_URL,
            wait_until="domcontentloaded",
            timeout=15000
        )

        print("Starting infinite scroll scraping...")

        previous_count = 0

        while True:

            # -------------------------------------------------
            # FORCE SCROLL TO BOTTOM
            # -------------------------------------------------

            page.evaluate("""
                window.scrollTo(
                    0,
                    document.body.scrollHeight
                )
            """)

            # WAIT FOR NEW PLAYERS TO LOAD
            page.wait_for_timeout(3000)

            # -------------------------------------------------
            # COLLECT PLAYER LINKS
            # -------------------------------------------------

            links = page.locator(
                'a[href*="/players/"]'
            ).all()

            for el in links:

                href = el.get_attribute("href")

                if not href:
                    continue

                clean_url = href.rstrip("/")

                # SKIP PAGINATION LINKS
                if "/page/" in clean_url:
                    continue

                # SKIP NON-PLAYER LINKS
                if clean_url.endswith("/players"):
                    continue

                # REMOVE #cs2 / #valorant etc
                clean_url = clean_url.split("#")[0]

                urls.add(clean_url)

            current_count = len(urls)

            print(f"Collected {current_count} player URLs")

            # -------------------------------------------------
            # STOP WHEN NO NEW PLAYERS LOAD
            # -------------------------------------------------

            if current_count == previous_count:

                print("No new players loaded.")

                break

            previous_count = current_count

        print(f"\nFINAL URL COUNT: {len(urls)}")

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

                page.goto(
                    url,
                    wait_until="commit",
                    timeout=10000
                )

                # WAIT ONLY FOR BIO CARD
                page.wait_for_selector(
                    "#bio",
                    timeout=5000
                )

                # -------------------------------------------------
                # BIO CARD
                # -------------------------------------------------

                bio = page.locator("#bio")

                # USERNAME
                username = bio.locator(
                    "h1"
                ).inner_text().strip()

                # -------------------------------------------------
                # TABLE DATA
                # -------------------------------------------------

                rows = bio.locator(
                    "table.data tr"
                )

                player_data = {}

                row_count = rows.count()

                for i in range(row_count):

                    row = rows.nth(i)

                    try:

                        header = row.locator(
                            "th"
                        ).inner_text().strip()

                        value = row.locator(
                            "td"
                        ).inner_text().strip()

                        player_data[header] = value

                    except:
                        continue

                # -------------------------------------------------
                # EXTRACT DATA
                # -------------------------------------------------

                actual_name = player_data.get(
                    "Name",
                    "Unknown"
                )

                birthday = player_data.get(
                    "Birthday",
                    "Unknown"
                )

                country = player_data.get(
                    "Country",
                    "Unknown"
                )

                team_name = player_data.get(
                    "Team",
                    "Free Agent"
                )

                if team_name == "":
                    team_name = "Free Agent"

                print(
                    f"SUCCESS: {username} | Team: {team_name}"
                )

                # -------------------------------------------------
                # PLAYER ATTRIBUTES
                # -------------------------------------------------

                player_attributes = json.dumps({
                    "full_name": actual_name,
                    "country": country,
                    "birthday": birthday,
                    "profile_url": url
                })

                # =================================================
                # DUPLICATE PREVENTION - PLAYER
                # =================================================

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
                    """, (
                        player_attributes,
                        player_id
                    ))

                else:

                    cursor = conn.execute("""
                        INSERT INTO Nodes
                        (NodeType, Name, Attributes)
                        VALUES (?, ?, ?)
                    """, (
                        "Player",
                        username,
                        player_attributes
                    ))

                    player_id = cursor.lastrowid

                # =================================================
                # DUPLICATE PREVENTION - TEAM
                # =================================================

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
                        INSERT INTO Nodes
                        (NodeType, Name, Attributes)
                        VALUES (?, ?, ?)
                    """, (
                        "Team",
                        team_name,
                        json.dumps({
                            "type": "organization"
                        })
                    ))

                    team_id = cursor.lastrowid

                # =================================================
                # DUPLICATE PREVENTION - EDGE
                # =================================================

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