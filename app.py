import sqlite3
import json
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- JINJA FILTERS ---
@app.template_filter('from_json')
def from_json_filter(value):
    try:
        return json.loads(value) if value else {}
    except:
        return {}

# --- DATABASE HELPER ---
def get_db_connection():
    conn = sqlite3.connect('esports.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- ROUTES ---

@app.route('/')
def index():
    conn = get_db_connection()
    nodes = conn.execute('SELECT COUNT(*) FROM Nodes').fetchone()[0]
    edges = conn.execute('SELECT COUNT(*) FROM Edges').fetchone()[0]
    conn.close()
    return render_template('index.html', counts={'nodes': nodes, 'edges': edges})

@app.route('/players')
def players_page():
    conn = get_db_connection()
    raw_players = conn.execute('SELECT * FROM Nodes WHERE NodeType = "Player"').fetchall()
    processed_players = []
    for p in raw_players:
        p_dict = dict(p)
        try:
            p_dict['attr'] = json.loads(p['Attributes'])
        except:
            p_dict['attr'] = {}
        processed_players.append(p_dict)
    conn.close()
    return render_template('players.html', players=processed_players)

@app.route('/teams', methods=['GET', 'POST'])
def teams():
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form['name']
        attrs = json.dumps({
            'game': request.form['game'],
            'location': request.form['location'],
            'founded': request.form.get('founded_year'),
            'ranking': request.form.get('ranking')
        })
        conn.execute('INSERT INTO Nodes (NodeType, Name, Attributes) VALUES (?, ?, ?)',
                     ('Team', name, attrs))
        conn.commit()
    
    raw_teams = conn.execute('SELECT * FROM Nodes WHERE NodeType = "Team"').fetchall()
    processed_teams = []
    for t in raw_teams:
        t_dict = dict(t)
        try:
            t_dict['attr'] = json.loads(t['Attributes'])
        except:
            t_dict['attr'] = {}
        processed_teams.append(t_dict)
    conn.close()
    return render_template('teams.html', teams=processed_teams)

@app.route('/tournaments', methods=['GET', 'POST'])
def tournaments():
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form['name']
        attrs = json.dumps({
            'country': request.form['country'],
            'year': request.form['founded_year'],
            'prize_pool': request.form['prize_pool']
        })
        conn.execute('INSERT INTO Nodes (NodeType, Name, Attributes) VALUES (?, ?, ?)',
                     ('Tournament', name, attrs))
        conn.commit()
    
    raw_tournaments = conn.execute('SELECT * FROM Nodes WHERE NodeType = "Tournament"').fetchall()
    processed_t = []
    for t in raw_tournaments:
        t_dict = dict(t)
        try:
            t_dict['attr'] = json.loads(t['Attributes'])
        except:
            t_dict['attr'] = {}
        processed_t.append(t_dict)
    conn.close()
    return render_template('tournaments.html', tournaments=processed_t)

@app.route('/plays_for', methods=['GET', 'POST'])
def plays_for():
    conn = get_db_connection()
    if request.method == 'POST':
        source = request.form['player_id']
        target = request.form['team_id']
        conn.execute('INSERT INTO Edges (SourceNodeID, TargetNodeID, EdgeType) VALUES (?, ?, ?)',
                     (source, target, 'Plays_For'))
        conn.commit()

    query = '''
        SELECT e.EdgeID, n1.Name as player_name, n2.Name as team_name
        FROM Edges e
        JOIN Nodes n1 ON e.SourceNodeID = n1.NodeID
        JOIN Nodes n2 ON e.TargetNodeID = n2.NodeID
        WHERE e.EdgeType = 'Plays_For'
    '''
    rows = conn.execute(query).fetchall()
    players = conn.execute('SELECT * FROM Nodes WHERE NodeType = "Player"').fetchall()
    teams = conn.execute('SELECT * FROM Nodes WHERE NodeType = "Team"').fetchall()
    conn.close()
    return render_template('plays_for.html', rows=rows, players=players, teams=teams)

@app.route('/played_in', methods=['GET', 'POST'])
def played_in():
    conn = get_db_connection()
    if request.method == 'POST':
        source = request.form['team_id']
        target = request.form['tournament_id']
        meta = json.dumps({'date': request.form.get('date_played')})
        conn.execute('INSERT INTO Edges (SourceNodeID, TargetNodeID, EdgeType, Metadata) VALUES (?, ?, ?, ?)',
                     (source, target, 'Played_In', meta))
        conn.commit()

    query = '''
        SELECT e.EdgeID, n1.Name as team_name, n2.Name as tournament_name, e.Metadata
        FROM Edges e
        JOIN Nodes n1 ON e.SourceNodeID = n1.NodeID
        JOIN Nodes n2 ON e.TargetNodeID = n2.NodeID
        WHERE e.EdgeType = 'Played_In'
    '''
    rows = conn.execute(query).fetchall()
    teams = conn.execute('SELECT * FROM Nodes WHERE NodeType = "Team"').fetchall()
    tournaments = conn.execute('SELECT * FROM Nodes WHERE NodeType = "Tournament"').fetchall()
    conn.close()
    return render_template('played_in.html', rows=rows, teams=teams, tournaments=tournaments)

@app.route('/reports', methods=['GET', 'POST'])
def reports_page():
    conn = get_db_connection()
    selected_player = None
    if request.method == 'POST':
        selected_player = request.form.get('player_name')
    
    players = conn.execute('SELECT Name FROM Nodes WHERE NodeType = "Player"').fetchall()
    conn.close()
    return render_template('reports.html', players=players, selected_player=selected_player)

@app.route('/api/graph-data/<player_name>')
def filtered_graph_data(player_name):
    """Returns only the selected player, their team(s), and fellow teammates."""
    conn = get_db_connection()
    
    # 1. Get the selected player's ID
    player = conn.execute('SELECT NodeID, Name FROM Nodes WHERE Name = ? AND NodeType = "Player"', (player_name,)).fetchone()
    if not player:
        conn.close()
        return jsonify({'elements': []})
    
    p_id = player['NodeID']

    # 2. Find the IDs of teams this player belongs to
    team_ids_query = 'SELECT TargetNodeID FROM Edges WHERE SourceNodeID = ? AND EdgeType = "Plays_For"'
    team_ids = [row['TargetNodeID'] for row in conn.execute(team_ids_query, (p_id,)).fetchall()]

    if not team_ids:
        # Return only the player node if they are teamless
        conn.close()
        return jsonify({'elements': [{'data': {'id': str(p_id), 'label': player['Name'], 'type': 'player'}}]})

    # 3. Get all 'Plays_For' edges for those teams (this captures teammates)
    placeholders = ','.join(['?'] * len(team_ids))
    edges_query = f'''
        SELECT e.SourceNodeID, e.TargetNodeID, n.Name as player_name
        FROM Edges e
        JOIN Nodes n ON e.SourceNodeID = n.NodeID
        WHERE e.TargetNodeID IN ({placeholders}) AND e.EdgeType = "Plays_For"
    '''
    relevant_edges = conn.execute(edges_query, team_ids).fetchall()

    # 4. Get the Team node details
    nodes_query = f'SELECT NodeID, Name FROM Nodes WHERE NodeID IN ({placeholders})'
    team_nodes = conn.execute(nodes_query, team_ids).fetchall()
    conn.close()

    # 5. Format for Cytoscape
    elements = []
    seen_nodes = set()

    # Add Teams
    for team in team_nodes:
        elements.append({'data': {'id': str(team['NodeID']), 'label': team['Name'], 'type': 'team'}})
        seen_nodes.add(team['NodeID'])

    # Add Players and Edges
    for edge in relevant_edges:
        player_id = edge['SourceNodeID']
        team_id = edge['TargetNodeID']
        
        if player_id not in seen_nodes:
            elements.append({'data': {'id': str(player_id), 'label': edge['player_name'], 'type': 'player'}})
            seen_nodes.add(player_id)
        
        elements.append({'data': {'source': str(player_id), 'target': str(team_id), 'label': 'Plays_For'}})

    return jsonify({'elements': elements})

if __name__ == '__main__':
    app.run(debug=True)