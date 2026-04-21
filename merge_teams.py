import sqlite3

def merge_duplicate_teams(db_path='esports.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Find names that appear more than once
    cursor.execute('''
        SELECT Name, COUNT(*) 
        FROM Nodes 
        WHERE NodeType = 'Team' 
        GROUP BY Name 
        HAVING COUNT(*) > 1
    ''')
    duplicates = cursor.fetchall()

    if not duplicates:
        print("No duplicate team names found.")
        return

    for name, count in duplicates:
        print(f"Merging {count} instances of '{name}'...")
        
        # Get all IDs for this team name, sorted by ID (lowest ID becomes Master)
        cursor.execute('SELECT NodeID FROM Nodes WHERE Name = ? AND NodeType = "Team" ORDER BY NodeID ASC', (name,))
        ids = [row[0] for row in cursor.fetchall()]
        
        master_id = ids[0]
        ghost_ids = ids[1:]

        for ghost_id in ghost_ids:
            # Update Edges where the ghost was the Source (e.g., Team played in Tournament)
            cursor.execute('UPDATE Edges SET SourceNodeID = ? WHERE SourceNodeID = ?', (master_id, ghost_id))
            
            # Update Edges where the ghost was the Target (e.g., Player belongs to Team)
            cursor.execute('UPDATE Edges SET TargetNodeID = ? WHERE TargetNodeID = ?', (master_id, ghost_id))
            
            # Delete the ghost node
            cursor.execute('DELETE FROM Nodes WHERE NodeID = ?', (ghost_id,))
            
        print(f"  ✅ '{name}' merged into ID: {master_id}")

    conn.commit()
    conn.close()
    print("\nDatabase cleaning complete.")

if __name__ == "__main__":
    merge_duplicate_teams()