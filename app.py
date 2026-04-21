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
GRAPH_DEFINITIONS = {
    1: {
        'name': 'Roster Graph',
        'description': 'Player-to-team affiliation graph built from Plays_For edges.'
    },
    2: {
        'name': 'Tournament Participation Graph',
        'description': 'Team-to-tournament participation and results graph built from Played_In and Won_By edges.'
    },
    3: {
        'name': 'Q1 Influence Graph',
        'description': 'Q1 tournament influence graph for top-tier tournaments and their linked teams.'
    }
}


def register_graph_membership(conn, graph_id, node_id=None, edge_id=None):
    if node_id is None and edge_id is None:
        return

    conn.execute(
        'INSERT OR IGNORE INTO GraphMemberships (GraphID, NodeID, EdgeID) VALUES (?, ?, ?)',
        (graph_id, node_id, edge_id)
    )


def parse_q1_tournament_ids(conn):
    tournaments = conn.execute('''
        SELECT NodeID, Attributes
        FROM Nodes
        WHERE NodeType = "Tournament"
    ''').fetchall()

    q1_ids = set()
    for tournament in tournaments:
        attrs = safe_json_load(tournament['Attributes'])
        if parse_prize_value(attrs.get('prize_pool')) > 1_000_000:
            q1_ids.add(tournament['NodeID'])

    return q1_ids


def backfill_graph_memberships(conn):
    edges = conn.execute('''
        SELECT EdgeID, SourceNodeID, TargetNodeID, EdgeType
        FROM Edges
    ''').fetchall()

    q1_ids = parse_q1_tournament_ids(conn)

    for edge in edges:
        edge_type = edge['EdgeType']
        source_id = edge['SourceNodeID']
        target_id = edge['TargetNodeID']
        edge_id = edge['EdgeID']

        if edge_type == 'Plays_For':
            register_graph_membership(conn, 1, edge_id=edge_id)
            register_graph_membership(conn, 1, node_id=source_id)
            register_graph_membership(conn, 1, node_id=target_id)

        if edge_type in ('Played_In', 'Won_By'):
            register_graph_membership(conn, 2, edge_id=edge_id)
            register_graph_membership(conn, 2, node_id=source_id)
            register_graph_membership(conn, 2, node_id=target_id)

        if edge_type in ('Played_In', 'Won_By') and source_id in q1_ids:
            register_graph_membership(conn, 3, edge_id=edge_id)
            register_graph_membership(conn, 3, node_id=source_id)
            register_graph_membership(conn, 3, node_id=target_id)


def ensure_graph_schema(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Graphs (
            GraphID INTEGER PRIMARY KEY,
            GraphName TEXT NOT NULL UNIQUE,
            Description TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS GraphMemberships (
            MembershipID INTEGER PRIMARY KEY AUTOINCREMENT,
            GraphID INTEGER NOT NULL,
            NodeID INTEGER,
            EdgeID INTEGER,
            FOREIGN KEY (GraphID) REFERENCES Graphs(GraphID),
            FOREIGN KEY (NodeID) REFERENCES Nodes(NodeID),
            FOREIGN KEY (EdgeID) REFERENCES Edges(EdgeID),
            CHECK (NodeID IS NOT NULL OR EdgeID IS NOT NULL)
        )
    ''')
    conn.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_node_unique
        ON GraphMemberships (GraphID, NodeID)
        WHERE NodeID IS NOT NULL
    ''')
    conn.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_edge_unique
        ON GraphMemberships (GraphID, EdgeID)
        WHERE EdgeID IS NOT NULL
    ''')

    for graph_id, graph in GRAPH_DEFINITIONS.items():
        conn.execute(
            'INSERT OR IGNORE INTO Graphs (GraphID, GraphName, Description) VALUES (?, ?, ?)',
            (graph_id, graph['name'], graph['description'])
        )

    backfill_graph_memberships(conn)
    conn.commit()


def get_db_connection():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, 'esports.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_graph_schema(conn)
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

    players = conn.execute(
        'SELECT Name FROM Nodes WHERE NodeType = "Player" ORDER BY Name'
    ).fetchall()

    nodes = conn.execute('SELECT COUNT(*) FROM Nodes').fetchone()[0]
    edges = conn.execute('SELECT COUNT(*) FROM Edges').fetchone()[0]

    conn.close()

    return render_template(
        'reports.html',
        players=players,
        counts={'nodes': nodes, 'edges': edges},
        active_page='reports'
    )

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
    return render_template('players.html', players=processed_players, active_page='players')

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
    return render_template('teams.html', teams=processed_teams, active_page='teams')

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
    return render_template('tournaments.html', tournaments=processed_t, active_page='tournaments')

@app.route('/plays_for', methods=['GET', 'POST'])
def plays_for():
    conn = get_db_connection()
    if request.method == 'POST':
        source = request.form['player_id']
        target = request.form['team_id']
        cursor = conn.execute(
            'INSERT INTO Edges (SourceNodeID, TargetNodeID, EdgeType) VALUES (?, ?, ?)',
            (source, target, 'Plays_For')
        )
        edge_id = cursor.lastrowid
        register_graph_membership(conn, 1, edge_id=edge_id)
        register_graph_membership(conn, 1, node_id=int(source))
        register_graph_membership(conn, 1, node_id=int(target))
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
    return render_template('plays_for.html', rows=rows, players=players, teams=teams, active_page='plays_for')

@app.route('/played_in', methods=['GET', 'POST'])
def played_in():
    conn = get_db_connection()
    if request.method == 'POST':
        tournament_id = request.form['tournament_id']
        team_id = request.form['team_id']
        meta = json.dumps({'date': request.form.get('date_played')})
        cursor = conn.execute(
            'INSERT INTO Edges (SourceNodeID, TargetNodeID, EdgeType, Metadata) VALUES (?, ?, ?, ?)',
            (tournament_id, team_id, 'Played_In', meta)
        )
        edge_id = cursor.lastrowid
        register_graph_membership(conn, 2, edge_id=edge_id)
        register_graph_membership(conn, 2, node_id=int(tournament_id))
        register_graph_membership(conn, 2, node_id=int(team_id))

        if int(tournament_id) in parse_q1_tournament_ids(conn):
            register_graph_membership(conn, 3, edge_id=edge_id)
            register_graph_membership(conn, 3, node_id=int(tournament_id))
            register_graph_membership(conn, 3, node_id=int(team_id))

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
    return render_template('played_in.html', rows=rows, teams=teams, tournaments=tournaments, active_page='played_in')

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
        participants=participants,
        active_page='tournaments'
    )

@app.route('/reports')
def reports_page():
    conn = get_db_connection()

    players = conn.execute(
        'SELECT Name FROM Nodes WHERE NodeType = "Player" ORDER BY Name'
    ).fetchall()

    nodes = conn.execute('SELECT COUNT(*) FROM Nodes').fetchone()[0]
    edges = conn.execute('SELECT COUNT(*) FROM Edges').fetchone()[0]

    conn.close()

    return render_template(
        'reports.html',
        players=players,
        counts={'nodes': nodes, 'edges': edges}
    )



@app.route('/api/graphs')
def graphs_data():
    conn = get_db_connection()
    graphs = conn.execute('''
        SELECT g.GraphID, g.GraphName, g.Description,
               COUNT(DISTINCT gm.NodeID) AS node_count,
               COUNT(DISTINCT gm.EdgeID) AS edge_count
        FROM Graphs g
        LEFT JOIN GraphMemberships gm ON g.GraphID = gm.GraphID
        GROUP BY g.GraphID, g.GraphName, g.Description
        ORDER BY g.GraphID
    ''').fetchall()

    payload = []
    for graph in graphs:
        payload.append({
            'graph_id': graph['GraphID'],
            'name': graph['GraphName'],
            'description': graph['Description'],
            'node_count': graph['node_count'],
            'edge_count': graph['edge_count']
        })

    conn.close()
    return jsonify({'graphs': payload})

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
        JOIN GraphMemberships gm ON gm.NodeID = n.NodeID
        WHERE gm.GraphID = 1
          AND n.NodeType IN ("Player", "Team")
        ORDER BY n.NodeType, n.Name
    ''').fetchall()

    edges = conn.execute('''
        SELECT DISTINCT e.EdgeID, e.SourceNodeID, e.TargetNodeID, e.EdgeType, e.Metadata
        FROM Edges e
        JOIN GraphMemberships gm ON gm.EdgeID = e.EdgeID
        WHERE gm.GraphID = 1
          AND e.EdgeType = "Plays_For"
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

    participant_counts = {
        row['SourceNodeID']: row['participant_count']
        for row in conn.execute(
            '''
            SELECT SourceNodeID, COUNT(DISTINCT TargetNodeID) AS participant_count
            FROM Edges
            WHERE EdgeType = "Played_In"
            GROUP BY SourceNodeID
            '''
        ).fetchall()
    }

    team_rows = conn.execute(
        '''
        SELECT NodeID, Name, NodeType, Attributes
        FROM Nodes
        WHERE NodeType = "Team"
        ORDER BY Name
        '''
    ).fetchall()

    if mode == 'winner':
        relationship_rows = conn.execute(
            '''
            SELECT e.EdgeID, e.SourceNodeID, e.TargetNodeID,
                   tr.Name AS tournament_name, tr.Attributes AS tournament_attributes
            FROM Edges e
            JOIN Nodes tr ON tr.NodeID = e.SourceNodeID
            WHERE e.EdgeType = "Won_By"
              AND tr.NodeType = "Tournament"
            ORDER BY tr.Name
            '''
        ).fetchall()
        metric_label = 'win_esports_index'
    else:
        relationship_rows = conn.execute(
            '''
            SELECT e.EdgeID, e.SourceNodeID, e.TargetNodeID,
                   tr.Name AS tournament_name, tr.Attributes AS tournament_attributes
            FROM Edges e
            JOIN Nodes tr ON tr.NodeID = e.SourceNodeID
            WHERE e.EdgeType = "Played_In"
              AND tr.NodeType = "Tournament"
            ORDER BY tr.Name
            '''
        ).fetchall()
        metric_label = 'participant_esports_index'

    team_to_relationships = {}
    for row in relationship_rows:
        team_to_relationships.setdefault(row['TargetNodeID'], []).append(row)

    qualifying_teams = []
    qualifying_tournament_ids = set()
    qualifying_edge_ids = set()

    for team in team_rows:
        relationships = team_to_relationships.get(team['NodeID'], [])
        qualifying_relationships = []

        for rel in relationships:
            participant_count = participant_counts.get(rel['SourceNodeID'], 0)
            if participant_count >= n:
                qualifying_relationships.append((rel, participant_count))

        if len(qualifying_relationships) >= n:
            attrs = safe_json_load(team['Attributes'])
            attrs[metric_label] = len(qualifying_relationships)
            attrs['qualifying_tournaments'] = len(qualifying_relationships)
            attrs['minimum_participants_per_tournament'] = n
            qualifying_teams.append({
                'NodeID': team['NodeID'],
                'Name': team['Name'],
                'NodeType': team['NodeType'],
                'Attributes': attrs,
                'total_count': len(qualifying_relationships)
            })

            for rel, participant_count in qualifying_relationships:
                qualifying_tournament_ids.add(rel['SourceNodeID'])
                qualifying_edge_ids.add(rel['EdgeID'])

    if not qualifying_teams:
        conn.close()
        return jsonify({'elements': []})

    tournament_lookup = {
        row['NodeID']: row
        for row in conn.execute(
            '''
            SELECT NodeID, Name, NodeType, Attributes
            FROM Nodes
            WHERE NodeType = "Tournament"
            '''
        ).fetchall()
    }

    edge_placeholders = ','.join(['?'] * len(qualifying_edge_ids))
    edge_lookup = {
        row['EdgeID']: row
        for row in conn.execute(
            f'''
            SELECT EdgeID, SourceNodeID, TargetNodeID, EdgeType
            FROM Edges
            WHERE EdgeID IN ({edge_placeholders})
            ''',
            tuple(qualifying_edge_ids)
        ).fetchall()
    }

    elements = []

    for team in qualifying_teams:
        elements.append({
            'data': {
                'id': str(team['NodeID']),
                'label': team['Name'],
                'type': 'team',
                'nodeType': team['NodeType'],
                'attributes': team['Attributes'],
                'count': team['total_count']
            }
        })

    for tournament_id in sorted(qualifying_tournament_ids, key=lambda tid: tournament_lookup[tid]['Name']):
        tournament = tournament_lookup[tournament_id]
        attrs = safe_json_load(tournament['Attributes'])
        attrs['participant_count'] = participant_counts.get(tournament_id, 0)
        elements.append({
            'data': {
                'id': str(tournament['NodeID']),
                'label': tournament['Name'],
                'type': 'tournament',
                'nodeType': tournament['NodeType'],
                'attributes': attrs
            }
        })

    for edge_id in sorted(qualifying_edge_ids):
        edge = edge_lookup[edge_id]
        elements.append({
            'data': {
                'id': f"q2e{edge['EdgeID']}",
                'source': str(edge['SourceNodeID']),
                'target': str(edge['TargetNodeID']),
                'edgeType': edge['EdgeType']
            }
        })

    conn.close()
    return jsonify({'elements': elements})

# --- QUERY 3 GRAPH API ---
@app.route('/api/graph-data/query3')
def query3_graph_data():
    conn = get_db_connection()

    q1_tournaments = conn.execute('''
        SELECT DISTINCT n.NodeID, n.Name, n.NodeType, n.Attributes
        FROM Nodes n
        JOIN GraphMemberships gm ON gm.NodeID = n.NodeID
        WHERE gm.GraphID = 3
          AND n.NodeType = "Tournament"
        ORDER BY n.Name
    ''').fetchall()

    team_nodes = conn.execute('''
        SELECT DISTINCT n.NodeID, n.Name, n.NodeType, n.Attributes
        FROM Nodes n
        JOIN GraphMemberships gm ON gm.NodeID = n.NodeID
        WHERE gm.GraphID = 3
          AND n.NodeType = "Team"
        ORDER BY n.Name
    ''').fetchall()

    edges = conn.execute('''
        SELECT DISTINCT e.EdgeID, e.SourceNodeID, e.TargetNodeID, e.EdgeType
        FROM Edges e
        JOIN GraphMemberships gm ON gm.EdgeID = e.EdgeID
        WHERE gm.GraphID = 3
          AND e.EdgeType IN ("Played_In", "Won_By")
        ORDER BY e.EdgeID
    ''').fetchall()

    if not q1_tournaments:
        conn.close()
        return jsonify({'elements': []})

    elements = []

    for tournament in q1_tournaments:
        elements.append({
            'data': {
                'id': str(tournament['NodeID']),
                'label': tournament['Name'],
                'type': 'tournament',
                'nodeType': tournament['NodeType'],
                'attributes': safe_json_load(tournament['Attributes'])
            }
        })

    for team in team_nodes:
        elements.append({
            'data': {
                'id': str(team['NodeID']),
                'label': team['Name'],
                'type': 'team',
                'nodeType': team['NodeType'],
                'attributes': safe_json_load(team['Attributes'])
            }
        })

    for edge in edges:
        elements.append({
            'data': {
                'id': f"q3e{edge['EdgeID']}",
                'source': str(edge['SourceNodeID']),
                'target': str(edge['TargetNodeID']),
                'edgeType': edge['EdgeType']
            }
        })

    conn.close()
    return jsonify({'elements': elements})

if __name__ == '__main__':
    app.run(debug=True)