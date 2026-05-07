import sqlite3
import json
import time
import re
import os
from playwright.sync_api import sync_playwright

TARGET_URLS = {
    "Valorant": "https://liquipedia.net/valorant/S-Tier_Tournaments",
    "Fortnite": "https://liquipedia.net/fortnite/S-Tier_Tournaments",
    "Dota2": "https://liquipedia.net/dota2/Tier_1_Tournaments",
    "CounterStrike": "https://liquipedia.net/counterstrike/S-Tier_Tournaments",
    "RainbowSix": "https://liquipedia.net/rainbowsix/S-Tier_Tournaments",
    "PUBG": "https://liquipedia.net/pubg/S-Tier_Tournaments",
    "ApexLegends": "https://liquipedia.net/apexlegends/S-Tier_Tournaments",
    "RocketLeague": "https://liquipedia.net/rocketleague/S-Tier_Tournaments",
    "LeagueOfLegends": "https://liquipedia.net/leagueoflegends/S-Tier_Tournaments"
}

DB_NAME = "esports.db"

def get_db_connection():

    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, DB_NAME)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    return conn

def clean_text(text):

    return " ".join(text.split()).strip()

def is_future_tournament(text):

    bad_words = ["TBD", "TBA"]

    for word in bad_words:
        if word in text:
            return True

    return False

def scrape_tournaments():

    conn = get_db_connection()
    cursor = conn.cursor()

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        context = browser.new_context(
            viewport={"width": 1600, "height": 1200}
        )

        page = context.new_page()

        for game_name, url in TARGET_URLS.items():

            print("\n==============================")
            print(f"SCRAPING {game_name}")
            print("==============================")

            page.goto(
                url,
                wait_until="networkidle",
                timeout=60000
            )

            time.sleep(4)

            rows = page.locator(
                "tr.table2__row--body"
            ).all()

            print(f"Found {len(rows)} total rows.")

            inserted_count = 0

            for row in rows:

                try:

                    row_class = row.get_attribute("class")

                    if not row_class:
                        continue

                    # ONLY GOLD HIGHLIGHTED TOURNAMENTS
                    if "table2__row--highlighted" not in row_class:
                        continue

                    # TOURNAMENT LINK
                    tournament_link = row.locator(
                        "td.column__tournament a"
                    ).first

                    if tournament_link.count() == 0:
                        continue

                    tournament_name = clean_text(
                        tournament_link.inner_text()
                    )

                    if not tournament_name:
                        continue

                    href = tournament_link.get_attribute("href")

                    if not href:
                        continue

                    tournament_url = (
                        "https://liquipedia.net" + href
                    )

                    # DATE
                    date = "Unknown"

                    try:
                        date = clean_text(
                            row.locator("td").nth(2).inner_text()
                        )
                    except:
                        pass

                    # PRIZE POOL
                    prize_pool = "Unknown"

                    try:
                        prize_pool = clean_text(
                            row.locator("td").nth(3).inner_text()
                        )
                    except:
                        pass

                    # LOCATION
                    location = "Unknown"

                    try:
                        location = clean_text(
                            row.locator("td").nth(4).inner_text()
                        )
                    except:
                        pass

                    # WINNER + RUNNER UP
                    winner = "Unknown"
                    runner_up = ""

                    try:

                        placement_cells = row.locator(
                            "td.column__placement"
                        ).all()

                        if len(placement_cells) > 0:

                            winner = clean_text(
                                placement_cells[0].inner_text()
                            )

                        if len(placement_cells) > 1:

                            runner_up = clean_text(
                                placement_cells[1].inner_text()
                            )

                    except:
                        pass

                    # SKIP FUTURE TOURNAMENTS
                    if is_future_tournament(winner):

                        print(
                            f"Skipping future tournament: {tournament_name}"
                        )

                        continue

                    # YEAR
                    year_match = re.search(
                        r"(20\d\d)",
                        date
                    )

                    year = (
                        year_match.group(1)
                        if year_match
                        else "Unknown"
                    )

                    print(f"\nTournament: {tournament_name}")
                    print(f"Winner: {winner}")

                    # ATTRIBUTES
                    attributes = {
                        "game": game_name,
                        "year": year,
                        "date": date,
                        "location": location,
                        "prize_pool": prize_pool,
                        "url": tournament_url,
                        "winner": winner,
                        "runner_up": runner_up,
                        "tier": "S-Tier"
                    }

                    attr_json = json.dumps(attributes)

                    # INSERT TOURNAMENT NODE
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO Nodes
                        (NodeType, Name, Attributes)
                        VALUES (?, ?, ?)
                        """,
                        (
                            "Tournament",
                            tournament_name,
                            attr_json
                        )
                    )

                    # UPDATE ATTRIBUTES
                    cursor.execute(
                        """
                        UPDATE Nodes
                        SET Attributes = ?
                        WHERE Name = ?
                        AND NodeType = 'Tournament'
                        """,
                        (
                            attr_json,
                            tournament_name
                        )
                    )

                    conn.commit()

                    # GET TOURNAMENT ID
                    tournament_id = conn.execute(
                        '''
                        SELECT NodeID
                        FROM Nodes
                        WHERE Name = ?
                        AND NodeType = "Tournament"
                        ''',
                        (tournament_name,)
                    ).fetchone()[0]

                    # INSERT WINNER TEAM
                    cursor.execute(
                        '''
                        INSERT OR IGNORE INTO Nodes
                        (NodeType, Name, Attributes)
                        VALUES (?, ?, ?)
                        ''',
                        (
                            "Team",
                            winner,
                            json.dumps({"game": game_name})
                        )
                    )

                    conn.commit()

                    # GET WINNER ID
                    winner_id = conn.execute(
                        '''
                        SELECT NodeID
                        FROM Nodes
                        WHERE Name = ?
                        AND NodeType = "Team"
                        ''',
                        (winner,)
                    ).fetchone()[0]

                    # INSERT WON_BY EDGE
                    cursor.execute(
                        '''
                        INSERT OR IGNORE INTO Edges
                        (SourceNodeID, TargetNodeID, EdgeType)
                        VALUES (?, ?, ?)
                        ''',
                        (
                            tournament_id,
                            winner_id,
                            "Won_By"
                        )
                    )

                    # INSERT PLAYED_IN EDGE FOR WINNER
                    cursor.execute(
                        '''
                        INSERT OR IGNORE INTO Edges
                        (SourceNodeID, TargetNodeID, EdgeType)
                        VALUES (?, ?, ?)
                        ''',
                        (
                            tournament_id,
                            winner_id,
                            "Played_In"
                        )
                    )

                    conn.commit()

                    # INSERT RUNNER UP TEAM
                    if runner_up and runner_up != "Unknown":

                        cursor.execute(
                            '''
                            INSERT OR IGNORE INTO Nodes
                            (NodeType, Name, Attributes)
                            VALUES (?, ?, ?)
                            ''',
                            (
                                "Team",
                                runner_up,
                                json.dumps({"game": game_name})
                            )
                        )

                        conn.commit()

                        runner_up_id = conn.execute(
                            '''
                            SELECT NodeID
                            FROM Nodes
                            WHERE Name = ?
                            AND NodeType = "Team"
                            ''',
                            (runner_up,)
                        ).fetchone()[0]

                        # INSERT PLAYED_IN EDGE FOR RUNNER UP
                        cursor.execute(
                            '''
                            INSERT OR IGNORE INTO Edges
                            (SourceNodeID, TargetNodeID, EdgeType)
                            VALUES (?, ?, ?)
                            ''',
                            (
                                tournament_id,
                                runner_up_id,
                                "Played_In"
                            )
                        )

                        conn.commit()

                    inserted_count += 1

                except Exception as e:

                    print(f"ROW ERROR: {e}")

            print(f"\nInserted {inserted_count} tournaments.")

        browser.close()

    conn.close()

    print("\n===================================")
    print("SCRAPING FINISHED")
    print("===================================")

if __name__ == "__main__":

    scrape_tournaments()