import sqlite3
import json
import os
import re
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

def parse_prize_value(raw_value):
    if raw_value is None:
        return 0.0

    text = str(raw_value).strip().upper()
    if not text:
        return 0.0

    multiplier = 1.0
    if 'M' in text:
        multiplier = 1_000_000.0
    elif 'K' in text:
        multiplier = 1_000.0

    cleaned = re.sub(r'[^0-9.]', '', text)
    if not cleaned:
        return 0.0

    try:
        return float(cleaned) * multiplier
    except ValueError:
        return 0.0

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

@app.route('/reports')
def reports_page():
    conn = get_db_connection()
    players = conn.execute(
        'SELECT Name FROM Nodes WHERE NodeType = "Player" ORDER BY Name'
    ).fetchall()
    conn.close()
    return render_template('reports.html', players=players)

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

# --- CLICK DETAILS API FOR ALL TABS ---
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

# --- QUERY 1 GRAPH API ---
@app.route('/api/graph-data/query1')
def query1_graph_data():
    conn = get_db_connection()

    nodes = conn.execute('''
        SELECT DISTINCT n.NodeID, n.Name, n.NodeType, n.Attributes
        FROM Nodes n
        JOIN (
            SELECT SourceNodeID AS NodeID FROM Edges WHERE EdgeType = "Plays_For"
            UNION
            SELECT TargetNodeID AS NodeID FROM Edges WHERE EdgeType = "Plays_For"
        ) used_nodes ON n.NodeID = used_nodes.NodeID
        WHERE n.NodeType IN ("Player", "Team")
        ORDER BY n.NodeType, n.Name
    ''').fetchall()

    edges = conn.execute('''
        SELECT EdgeID, SourceNodeID, TargetNodeID, EdgeType, Metadata
        FROM Edges
        WHERE EdgeType = "Plays_For"
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
                'id': f"q1e{edge['EdgeID']}",
                'source': str(edge['SourceNodeID']),
                'target': str(edge['TargetNodeID'])
            }
        })

    conn.close()
    return jsonify({'elements': elements})

# --- QUERY 2 GRAPH API ---
@app.route('/api/graph-data/query2')
def query2_graph_data():
    mode = request.args.get('mode', 'participant').strip().lower()

    try:
        n = int(request.args.get('n', 2))
    except (TypeError, ValueError):
        n = 2

    if n < 1:
        n = 1

    conn = get_db_connection()

    if mode == 'winner':
        qualifying_teams = conn.execute('''
            SELECT t.NodeID, t.Name, t.NodeType, t.Attributes,
                   COUNT(DISTINCT e.SourceNodeID) AS total_count
            FROM Nodes t
            JOIN Edges e
              ON e.TargetNodeID = t.NodeID
            WHERE t.NodeType = "Team"
              AND e.EdgeType = "Won_By"
            GROUP BY t.NodeID, t.Name, t.NodeType, t.Attributes
            HAVING COUNT(DISTINCT e.SourceNodeID) >= ?
            ORDER BY total_count DESC, t.Name
        ''', (n,)).fetchall()

        team_ids = [row['NodeID'] for row in qualifying_teams]

        if not team_ids:
            conn.close()
            return jsonify({'elements': []})

        placeholders = ','.join(['?'] * len(team_ids))

        tournaments = conn.execute(f'''
            SELECT DISTINCT tr.NodeID, tr.Name, tr.NodeType, tr.Attributes
            FROM Nodes tr
            JOIN Edges e
              ON e.SourceNodeID = tr.NodeID
            WHERE tr.NodeType = "Tournament"
              AND e.EdgeType = "Won_By"
              AND e.TargetNodeID IN ({placeholders})
            ORDER BY tr.Name
        ''', team_ids).fetchall()

        edges = conn.execute(f'''
            SELECT EdgeID, SourceNodeID, TargetNodeID
            FROM Edges
            WHERE EdgeType = "Won_By"
              AND TargetNodeID IN ({placeholders})
        ''', team_ids).fetchall()

    else:
        qualifying_teams = conn.execute('''
            SELECT t.NodeID, t.Name, t.NodeType, t.Attributes,
                   COUNT(DISTINCT e.SourceNodeID) AS total_count
            FROM Nodes t
            JOIN Edges e
              ON e.TargetNodeID = t.NodeID
            WHERE t.NodeType = "Team"
              AND e.EdgeType = "Played_In"
            GROUP BY t.NodeID, t.Name, t.NodeType, t.Attributes
            HAVING COUNT(DISTINCT e.SourceNodeID) >= ?
            ORDER BY total_count DESC, t.Name
        ''', (n,)).fetchall()

        team_ids = [row['NodeID'] for row in qualifying_teams]

        if not team_ids:
            conn.close()
            return jsonify({'elements': []})

        placeholders = ','.join(['?'] * len(team_ids))

        tournaments = conn.execute(f'''
            SELECT DISTINCT tr.NodeID, tr.Name, tr.NodeType, tr.Attributes
            FROM Nodes tr
            JOIN Edges e
              ON e.SourceNodeID = tr.NodeID
            WHERE tr.NodeType = "Tournament"
              AND e.EdgeType = "Played_In"
              AND e.TargetNodeID IN ({placeholders})
            ORDER BY tr.Name
        ''', team_ids).fetchall()

        edges = conn.execute(f'''
            SELECT EdgeID, SourceNodeID, TargetNodeID
            FROM Edges
            WHERE EdgeType = "Played_In"
              AND TargetNodeID IN ({placeholders})
        ''', team_ids).fetchall()

    elements = []

    for team in qualifying_teams:
        attrs = safe_json_load(team['Attributes'])
        attrs['threshold_count'] = team['total_count']
        elements.append({
            'data': {
                'id': str(team['NodeID']),
                'label': team['Name'],
                'type': 'team',
                'nodeType': team['NodeType'],
                'attributes': attrs,
                'count': team['total_count']
            }
        })

    for tournament in tournaments:
        attrs = safe_json_load(tournament['Attributes'])
        elements.append({
            'data': {
                'id': str(tournament['NodeID']),
                'label': tournament['Name'],
                'type': 'tournament',
                'nodeType': tournament['NodeType'],
                'attributes': attrs
            }
        })

    for edge in edges:
        elements.append({
            'data': {
                'id': f"q2e{edge['EdgeID']}",
                'source': str(edge['SourceNodeID']),
                'target': str(edge['TargetNodeID'])
            }
        })

    conn.close()
    return jsonify({'elements': elements})

# --- QUERY 3 GRAPH API ---
@app.route('/api/graph-data/query3')
def query3_graph_data():
    conn = get_db_connection()

    all_tournaments = conn.execute('''
        SELECT NodeID, Name, NodeType, Attributes
        FROM Nodes
        WHERE NodeType = "Tournament"
        ORDER BY Name
    ''').fetchall()

    q1_tournaments = []

    for tournament in all_tournaments:
        attrs = safe_json_load(tournament['Attributes'])
        prize_value = parse_prize_value(attrs.get('prize_pool'))

        if prize_value > 1_000_000:
            q1_tournaments.append((tournament, attrs))

    if not q1_tournaments:
        conn.close()
        return jsonify({'elements': []})

    elements = []
    added_node_ids = set()
    added_edge_ids = set()

    for tournament, attrs in q1_tournaments:
        tournament_id = tournament['NodeID']

        if tournament_id not in added_node_ids:
            elements.append({
                'data': {
                    'id': str(tournament_id),
                    'label': tournament['Name'],
                    'type': 'tournament',
                    'nodeType': tournament['NodeType'],
                    'attributes': attrs
                }
            })
            added_node_ids.add(tournament_id)

        participant_edges = conn.execute('''
            SELECT EdgeID, SourceNodeID, TargetNodeID, EdgeType
            FROM Edges
            WHERE EdgeType = "Played_In"
              AND SourceNodeID = ?
        ''', (tournament_id,)).fetchall()

        # Fallback: if a Q1 tournament has no Played_In rows yet,
        # still show its winner team so the graph is not tournament-only.
        relevant_edges = participant_edges
        if not relevant_edges:
            relevant_edges = conn.execute('''
                SELECT EdgeID, SourceNodeID, TargetNodeID, EdgeType
                FROM Edges
                WHERE EdgeType = "Won_By"
                  AND SourceNodeID = ?
            ''', (tournament_id,)).fetchall()

        for edge in relevant_edges:
            team = conn.execute('''
                SELECT NodeID, Name, NodeType, Attributes
                FROM Nodes
                WHERE NodeID = ?
                  AND NodeType = "Team"
            ''', (edge['TargetNodeID'],)).fetchone()

            if not team:
                continue

            if team['NodeID'] not in added_node_ids:
                elements.append({
                    'data': {
                        'id': str(team['NodeID']),
                        'label': team['Name'],
                        'type': 'team',
                        'nodeType': team['NodeType'],
                        'attributes': safe_json_load(team['Attributes'])
                    }
                })
                added_node_ids.add(team['NodeID'])

            edge_id = f"q3e{edge['EdgeID']}"
            if edge_id not in added_edge_ids:
                elements.append({
                    'data': {
                        'id': edge_id,
                        'source': str(edge['SourceNodeID']),
                        'target': str(edge['TargetNodeID']),
                        'edgeType': edge['EdgeType']
                    }
                })
                added_edge_ids.add(edge_id)

    conn.close()
    return jsonify({'elements': elements})

if __name__ == '__main__':
    app.run(debug=True)