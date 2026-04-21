import sqlite3
import json
import os
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- JINJA FILTERS ---
@app.template_filter('from_json')
def from_json_filter(value):
    try:
        return json.loads(value) if value else {}
    except (json.JSONDecodeError, TypeError):
        return {}

# --- DATABASE HELPER ---
def get_db_connection():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, 'esports.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# --- SMALL HELPERS ---
def safe_json_load(value):
    try:
        return json.loads(value) if value else {}
    except (json.JSONDecodeError, TypeError):
        return {}

def get_connected_nodes(conn, node_id):
    query = '''
        SELECT DISTINCT n.NodeID, n.Name, n.NodeType, e.EdgeType
        FROM Edges e
        JOIN Nodes n
          ON (
              (e.SourceNodeID = ? AND n.NodeID = e.TargetNodeID)
              OR
              (e.TargetNodeID = ? AND n.NodeID = e.SourceNodeID)
          )
        WHERE e.SourceNodeID = ? OR e.TargetNodeID = ?
        ORDER BY n.NodeType, n.Name
    '''
    return conn.execute(query, (node_id, node_id, node_id, node_id)).fetchall()

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
        p_dict['attr'] = from_json_filter(p['Attributes'])
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
        conn.execute(
            'INSERT INTO Nodes (NodeType, Name, Attributes) VALUES (?, ?, ?)',
            ('Team', name, attrs)
        )
        conn.commit()

    raw_teams = conn.execute('SELECT * FROM Nodes WHERE NodeType = "Team"').fetchall()
    processed_teams = []
    for t in raw_teams:
        t_dict = dict(t)
        t_dict['attr'] = from_json_filter(t['Attributes'])
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
        conn.execute(
            'INSERT INTO Nodes (NodeType, Name, Attributes) VALUES (?, ?, ?)',
            ('Tournament', name, attrs)
        )
        conn.commit()

    raw_tournaments = conn.execute('SELECT * FROM Nodes WHERE NodeType = "Tournament"').fetchall()
    processed_t = []
    for t in raw_tournaments:
        t_dict = dict(t)
        t_dict['attr'] = from_json_filter(t['Attributes'])
        processed_t.append(t_dict)
    conn.close()
    return render_template('tournaments.html', tournaments=processed_t)

@app.route('/plays_for', methods=['GET', 'POST'])
def plays_for():
    conn = get_db_connection()
    if request.method == 'POST':
        source = request.form['player_id']
        target = request.form['team_id']
        conn.execute(
            'INSERT INTO Edges (SourceNodeID, TargetNodeID, EdgeType) VALUES (?, ?, ?)',
            (source, target, 'Plays_For')
        )
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
        tournament_id = request.form['tournament_id']
        team_id = request.form['team_id']
        meta = json.dumps({'date': request.form.get('date_played')})
        conn.execute(
            'INSERT INTO Edges (SourceNodeID, TargetNodeID, EdgeType, Metadata) VALUES (?, ?, ?, ?)',
            (tournament_id, team_id, 'Played_In', meta)
        )
        conn.commit()

    query = '''
        SELECT e.EdgeID, n1.Name as tournament_name, n2.Name as team_name, e.Metadata
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

@app.route('/tournament/<int:node_id>')
def tournament_details(node_id):
    conn = get_db_connection()

    tournament = conn.execute(
        'SELECT * FROM Nodes WHERE NodeID = ?',
        (node_id,)
    ).fetchone()

    if not tournament:
        conn.close()
        return "Tournament not found", 404

    details = from_json_filter(tournament['Attributes'])

    winner = conn.execute('''
        SELECT Nodes.Name, Nodes.NodeID
        FROM Nodes
        JOIN Edges ON Nodes.NodeID = Edges.TargetNodeID
        WHERE Edges.SourceNodeID = ? AND Edges.EdgeType = "Won_By"
    ''', (node_id,)).fetchone()

    participants = conn.execute('''
        SELECT Nodes.Name, Nodes.NodeID
        FROM Nodes
        JOIN Edges ON Nodes.NodeID = Edges.TargetNodeID
        WHERE Edges.SourceNodeID = ? AND Edges.EdgeType = "Played_In"
        ORDER BY Nodes.Name ASC
    ''', (node_id,)).fetchall()

    conn.close()
    return render_template(
        'tournament_details.html',
        tournament=tournament,
        details=details,
        winner=winner,
        participants=participants
    )

@app.route('/reports', methods=['GET', 'POST'])
def reports_page():
    conn = get_db_connection()
    selected_player = None
    if request.method == 'POST':
        selected_player = request.form.get('player_name')

    players = conn.execute(
        'SELECT Name FROM Nodes WHERE NodeType = "Player" ORDER BY Name'
    ).fetchall()
    conn.close()
    return render_template('reports.html', players=players, selected_player=selected_player)

# --- OVERVIEW GRAPH API ---
@app.route('/api/graph-data/all')
def all_graph_data():
    conn = get_db_connection()

    nodes = conn.execute('''
        SELECT NodeID, Name, NodeType, Attributes
        FROM Nodes
        WHERE NodeType IN ("Player", "Team", "Tournament")
        ORDER BY NodeType, Name
    ''').fetchall()

    edges = conn.execute('''
        SELECT EdgeID, SourceNodeID, TargetNodeID, EdgeType, Metadata
        FROM Edges
        WHERE EdgeType IN ("Plays_For", "Played_In", "Won_By")
    ''').fetchall()

    elements = []

    for node in nodes:
        attrs = safe_json_load(node['Attributes'])
        elements.append({
            'data': {
                'id': str(node['NodeID']),
                'label': node['Name'],
                'type': node['NodeType'].lower(),
                'nodeType': node['NodeType'],
                'attributes': attrs
            }
        })

    for edge in edges:
        elements.append({
            'data': {
                'id': f"e{edge['EdgeID']}",
                'source': str(edge['SourceNodeID']),
                'target': str(edge['TargetNodeID']),
                'label': edge['EdgeType'],
                'edgeType': edge['EdgeType'],
                'metadata': safe_json_load(edge['Metadata'])
            }
        })

    conn.close()
    return jsonify({'elements': elements})

# --- CLICK DETAILS API FOR OVERVIEW GRAPH ---
@app.route('/api/node-details/<int:node_id>')
def node_details(node_id):
    conn = get_db_connection()

    node = conn.execute('''
        SELECT NodeID, Name, NodeType, Attributes
        FROM Nodes
        WHERE NodeID = ?
    ''', (node_id,)).fetchone()

    if not node:
        conn.close()
        return jsonify({'error': 'Node not found'}), 404

    attrs = safe_json_load(node['Attributes'])
    connected = get_connected_nodes(conn, node_id)

    connections = [
        {
            'id': row['NodeID'],
            'name': row['Name'],
            'type': row['NodeType'],
            'via': row['EdgeType']
        }
        for row in connected
    ]

    conn.close()
    return jsonify({
        'id': node['NodeID'],
        'name': node['Name'],
        'type': node['NodeType'],
        'attributes': attrs,
        'connections': connections
    })

# --- EXISTING PLAYER SUBGRAPH API ---
@app.route('/api/graph-data/<player_name>')
def filtered_graph_data(player_name):
    conn = get_db_connection()
    player = conn.execute(
        'SELECT NodeID, Name FROM Nodes WHERE Name = ? AND NodeType = "Player"',
        (player_name,)
    ).fetchone()

    if not player:
        conn.close()
        return jsonify({'elements': []})

    p_id = player['NodeID']
    team_ids_query = 'SELECT TargetNodeID FROM Edges WHERE SourceNodeID = ? AND EdgeType = "Plays_For"'
    team_ids = [row['TargetNodeID'] for row in conn.execute(team_ids_query, (p_id,)).fetchall()]

    if not team_ids:
        conn.close()
        return jsonify({
            'elements': [
                {'data': {'id': str(p_id), 'label': player['Name'], 'type': 'player'}}
            ]
        })

    placeholders = ','.join(['?'] * len(team_ids))
    edges_query = f'''
        SELECT e.SourceNodeID, e.TargetNodeID, n.Name as player_name
        FROM Edges e
        JOIN Nodes n ON e.SourceNodeID = n.NodeID
        WHERE e.TargetNodeID IN ({placeholders}) AND e.EdgeType = "Plays_For"
    '''
    relevant_edges = conn.execute(edges_query, team_ids).fetchall()
    team_nodes = conn.execute(
        f'SELECT NodeID, Name FROM Nodes WHERE NodeID IN ({placeholders})',
        team_ids
    ).fetchall()
    conn.close()

    elements = []
    seen_nodes = set()

    for team in team_nodes:
        elements.append({
            'data': {
                'id': str(team['NodeID']),
                'label': team['Name'],
                'type': 'team'
            }
        })
        seen_nodes.add(team['NodeID'])

    for edge in relevant_edges:
        player_id = edge['SourceNodeID']
        team_id = edge['TargetNodeID']
        if player_id not in seen_nodes:
            elements.append({
                'data': {
                    'id': str(player_id),
                    'label': edge['player_name'],
                    'type': 'player'
                }
            })
            seen_nodes.add(player_id)
        elements.append({
            'data': {
                'source': str(player_id),
                'target': str(team_id),
                'label': 'Plays_For'
            }
        })

    return jsonify({'elements': elements})

if __name__ == '__main__':
    app.run(debug=True)