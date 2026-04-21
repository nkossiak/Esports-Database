import sqlite3, json
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)
DATABASE = Path("esports.db")

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# --- CORE ROUTES ---

@app.route('/')
def index():
    conn = get_db_connection()
    counts = {
        'nodes': conn.execute('SELECT COUNT(*) FROM Nodes').fetchone()[0],
        'edges': conn.execute('SELECT COUNT(*) FROM Edges').fetchone()[0]
    }
    conn.close()
    return render_template('index.html', counts=counts)

@app.route('/players', methods=['GET', 'POST'])
def players():
    conn = get_db_connection()
    if request.method == 'POST':
        attrs = json.dumps({'username': request.form['username'], 'country': request.form['country']})
        conn.execute('INSERT INTO Nodes (NodeType, Name, Attributes) VALUES (?, ?, ?)', 
                     ('Player', request.form['name'], attrs))
        conn.commit()
    players_list = conn.execute("SELECT * FROM Nodes WHERE NodeType = 'Player'").fetchall()
    conn.close()
    return render_template('players.html', players=players_list)

@app.route('/teams', methods=['GET', 'POST'])
def teams():
    conn = get_db_connection()
    if request.method == 'POST':
        attrs = json.dumps({'game': request.form['game'], 'location': request.form['location']})
        conn.execute('INSERT INTO Nodes (NodeType, Name, Attributes) VALUES (?, ?, ?)', 
                     ('Team', request.form['name'], attrs))
        conn.commit()
    teams_list = conn.execute("SELECT * FROM Nodes WHERE NodeType = 'Team'").fetchall()
    conn.close()
    return render_template('teams.html', teams=teams_list)

@app.route('/tournaments', methods=['GET', 'POST'])
def tournaments():
    conn = get_db_connection()
    if request.method == 'POST':
        attrs = json.dumps({'prize_pool': request.form['prize_pool']})
        conn.execute('INSERT INTO Nodes (NodeType, Name, Attributes) VALUES (?, ?, ?)', 
                     ('Tournament', request.form['name'], attrs))
        conn.commit()
    tournaments_list = conn.execute("SELECT * FROM Nodes WHERE NodeType = 'Tournament'").fetchall()
    conn.close()
    return render_template('tournaments.html', tournaments=tournaments_list)

@app.route('/plays_for', methods=['GET', 'POST'])
def plays_for():
    conn = get_db_connection()
    if request.method == 'POST':
        meta = json.dumps({'date_joined': request.form['date_joined']})
        conn.execute('INSERT INTO Edges (SourceNodeID, TargetNodeID, EdgeType, Metadata) VALUES (?, ?, ?, ?)',
                     (request.form['player_id'], request.form['team_id'], 'Plays_For', meta))
        conn.commit()
    players = conn.execute("SELECT * FROM Nodes WHERE NodeType = 'Player'").fetchall()
    teams = conn.execute("SELECT * FROM Nodes WHERE NodeType = 'Team'").fetchall()
    rows = conn.execute('''
        SELECT E.EdgeID, N1.Name as player_name, N2.Name as team_name, E.Metadata
        FROM Edges E
        JOIN Nodes N1 ON E.SourceNodeID = N1.NodeID
        JOIN Nodes N2 ON E.TargetNodeID = N2.NodeID
        WHERE E.EdgeType = 'Plays_For'
    ''').fetchall()
    conn.close()
    return render_template('plays_for.html', players=players, teams=teams, rows=rows)

@app.route('/played_in', methods=['GET', 'POST'])
def played_in():
    conn = get_db_connection()
    if request.method == 'POST':
        meta = json.dumps({'date': request.form['date_played']})
        conn.execute('INSERT INTO Edges (SourceNodeID, TargetNodeID, EdgeType, Metadata) VALUES (?, ?, ?, ?)',
                     (request.form['team_id'], request.form['tournament_id'], 'Played_In', meta))
        conn.commit()
    teams = conn.execute("SELECT * FROM Nodes WHERE NodeType = 'Team'").fetchall()
    tourneys = conn.execute("SELECT * FROM Nodes WHERE NodeType = 'Tournament'").fetchall()
    rows = conn.execute('''
        SELECT E.EdgeID, N1.Name as team_name, N2.Name as tournament_name, E.Metadata
        FROM Edges E
        JOIN Nodes N1 ON E.SourceNodeID = N1.NodeID
        JOIN Nodes N2 ON E.TargetNodeID = N2.NodeID
        WHERE E.EdgeType = 'Played_In'
    ''').fetchall()
    conn.close()
    return render_template('played_in.html', teams=teams, tournaments=tourneys, rows=rows)

@app.route('/reports', methods=['GET', 'POST'])
def reports():
    conn = get_db_connection()
    players = conn.execute("SELECT Name FROM Nodes WHERE NodeType = 'Player'").fetchall()
    selected_player = request.form.get('player_name') if request.method == 'POST' else None
    
    # Q2: h-index check (mocked for graph)
    h_index = conn.execute("SELECT Name, NodeType FROM Nodes LIMIT 5").fetchall()
    
    conn.close()
    return render_template('reports.html', players=players, selected_player=selected_player, h_index_authors=h_index)

@app.route('/graph-data/<player_name>')
def graph_data(player_name):
    conn = get_db_connection()
    query = '''
        SELECT N2.Name as target, 'team' as type FROM Nodes N1
        JOIN Edges E1 ON N1.NodeID = E1.SourceNodeID
        JOIN Nodes N2 ON E1.TargetNodeID = N2.NodeID
        WHERE N1.Name = ? AND E1.EdgeType = 'Plays_For'
    '''
    results = conn.execute(query, (player_name,)).fetchall()
    elements = [{'data': {'id': player_name, 'label': player_name, 'type': 'player'}}]
    for row in results:
        elements.append({'data': {'id': row['target'], 'label': row['target'], 'type': row['type']}})
        elements.append({'data': {'source': player_name, 'target': row['target']}})
    return {'elements': elements}

if __name__ == '__main__':
    app.run(debug=True)