import sqlite3

def debug():
    conn = sqlite3.connect('esports.db')
    cursor = conn.cursor()
    
    # Check total counts
    played_in_count = cursor.execute("SELECT COUNT(*) FROM Edges WHERE EdgeType = 'Played_In'").fetchone()[0]
    won_by_count = cursor.execute("SELECT COUNT(*) FROM Edges WHERE EdgeType = 'Won_By'").fetchone()[0]
    
    print(f"--- Database Stats ---")
    print(f"Total 'Played_In' Edges: {played_in_count}")
    print(f"Total 'Won_By' Edges:    {won_by_count}")
    
    if played_in_count > 0:
        print(f"\n--- Sample Data (First 5 'Played_In') ---")
        samples = cursor.execute("""
            SELECT T.Name, Team.Name 
            FROM Edges E
            JOIN Nodes T ON E.SourceNodeID = T.NodeID
            JOIN Nodes Team ON E.TargetNodeID = Team.NodeID
            WHERE E.EdgeType = 'Played_In'
            LIMIT 5
        """).fetchall()
        for t, team in samples:
            print(f"Tournament: {t} | Participant: {team}")
    else:
        print("\n[!] No 'Played_In' edges found. The scraper likely missed the participant cards.")

    conn.close()

if __name__ == "__main__":
    debug()