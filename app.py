from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / 'esports.db'

app = Flask(__name__)
app.secret_key = 'dev-key-change-later'


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn


def init_db():
    schema_path = BASE_DIR / 'schema.sql'
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = f.read()
    conn = get_db_connection()
    conn.executescript(schema)
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db_connection()

    players = [
        ('TenZ', 'TenZ', 'Canada', 2001, 2020),
        ('Aspas', 'aspas', 'Brazil', 2003, 2021),
        ('Faker', 'Faker', 'South Korea', 1996, 2013),
    ]
    teams = [
        ('Sentinels', 'Valorant', 'USA', 2020, 1),
        ('LOUD', 'Valorant', 'Brazil', 2022, 2),
        ('T1', 'League of Legends', 'South Korea', 2003, 1),
    ]
    tournaments = [
        ('VCT Masters Madrid', 'Spain', 2024, 1, 500000),
        ('VALORANT Champions', 'South Korea', 2024, 1, 1000000),
        ('Worlds', 'South Korea', 2024, 1, 2225000),
    ]

    conn.executemany(
        '''INSERT OR IGNORE INTO players (name, username, country, birth_year, first_year)
           VALUES (?, ?, ?, ?, ?)''',
        players,
    )
    conn.executemany(
        '''INSERT OR IGNORE INTO teams (name, game, location, founded_year, ranking)
           VALUES (?, ?, ?, ?, ?)''',
        teams,
    )
    conn.executemany(
        '''INSERT OR IGNORE INTO tournaments (name, country, founded_year, ranking, prize_pool)
           VALUES (?, ?, ?, ?, ?)''',
        tournaments,
    )

    player_map = {
        row['username']: row['player_id']
        for row in conn.execute('SELECT player_id, username FROM players')
    }
    team_map = {
        row['name']: row['team_id']
        for row in conn.execute('SELECT team_id, name FROM teams')
    }
    tournament_map = {
        row['name']: row['tournament_id']
        for row in conn.execute('SELECT tournament_id, name FROM tournaments')
    }

    plays_for = [
        (player_map['TenZ'], team_map['Sentinels'], '2024-01-01', None),
        (player_map['aspas'], team_map['LOUD'], '2024-01-01', None),
        (player_map['Faker'], team_map['T1'], '2013-01-01', None),
    ]
    played_in = [
        (team_map['Sentinels'], tournament_map['VCT Masters Madrid'], '2024-03-20'),
        (team_map['LOUD'], tournament_map['VALORANT Champions'], '2024-08-15'),
        (team_map['T1'], tournament_map['Worlds'], '2024-11-02'),
    ]

    conn.executemany(
        '''INSERT OR IGNORE INTO plays_for (player_id, team_id, date_joined, date_left)
           VALUES (?, ?, ?, ?)''',
        plays_for,
    )
    conn.executemany(
        '''INSERT OR IGNORE INTO played_in (team_id, tournament_id, date_played)
           VALUES (?, ?, ?)''',
        played_in,
    )

    conn.commit()
    conn.close()


@app.route('/')
def index():
    conn = get_db_connection()

    counts = {
        'players': conn.execute('SELECT COUNT(*) AS count FROM players').fetchone()['count'],
        'teams': conn.execute('SELECT COUNT(*) AS count FROM teams').fetchone()['count'],
        'tournaments': conn.execute('SELECT COUNT(*) AS count FROM tournaments').fetchone()['count'],
        'plays_for': conn.execute('SELECT COUNT(*) AS count FROM plays_for').fetchone()['count'],
        'played_in': conn.execute('SELECT COUNT(*) AS count FROM played_in').fetchone()['count'],
    }

    roster = conn.execute(
        '''SELECT p.name AS player_name, p.username, t.name AS team_name, pf.date_joined, pf.date_left
           FROM plays_for pf
           JOIN players p ON pf.player_id = p.player_id
           JOIN teams t ON pf.team_id = t.team_id
           ORDER BY t.name, p.name'''
    ).fetchall()

    appearances = conn.execute(
        '''SELECT t.name AS team_name, tr.name AS tournament_name, pi.date_played
           FROM played_in pi
           JOIN teams t ON pi.team_id = t.team_id
           JOIN tournaments tr ON pi.tournament_id = tr.tournament_id
           ORDER BY pi.date_played DESC'''
    ).fetchall()

    conn.close()
    return render_template('index.html', counts=counts, roster=roster, appearances=appearances)


@app.route('/players', methods=['GET', 'POST'])
def players():
    conn = get_db_connection()
    if request.method == 'POST':
        conn.execute(
            '''INSERT INTO players (name, username, country, birth_year, first_year)
               VALUES (?, ?, ?, ?, ?)''',
            (
                request.form['name'],
                request.form['username'],
                request.form['country'],
                request.form['birth_year'] or None,
                request.form['first_year'] or None,
            ),
        )
        conn.commit()
        flash('Player added.')
        conn.close()
        return redirect(url_for('players'))

    rows = conn.execute('SELECT * FROM players ORDER BY name').fetchall()
    conn.close()
    return render_template('players.html', players=rows)


@app.route('/teams', methods=['GET', 'POST'])
def teams():
    conn = get_db_connection()
    if request.method == 'POST':
        conn.execute(
            '''INSERT INTO teams (name, game, location, founded_year, ranking)
               VALUES (?, ?, ?, ?, ?)''',
            (
                request.form['name'],
                request.form['game'],
                request.form['location'],
                request.form['founded_year'] or None,
                request.form['ranking'] or None,
            ),
        )
        conn.commit()
        flash('Team added.')
        conn.close()
        return redirect(url_for('teams'))

    rows = conn.execute('SELECT * FROM teams ORDER BY name').fetchall()
    conn.close()
    return render_template('teams.html', teams=rows)


@app.route('/tournaments', methods=['GET', 'POST'])
def tournaments():
    conn = get_db_connection()
    if request.method == 'POST':
        conn.execute(
            '''INSERT INTO tournaments (name, country, founded_year, ranking, prize_pool)
               VALUES (?, ?, ?, ?, ?)''',
            (
                request.form['name'],
                request.form['country'],
                request.form['founded_year'] or None,
                request.form['ranking'] or None,
                request.form['prize_pool'] or None,
            ),
        )
        conn.commit()
        flash('Tournament added.')
        conn.close()
        return redirect(url_for('tournaments'))

    rows = conn.execute('SELECT * FROM tournaments ORDER BY name').fetchall()
    conn.close()
    return render_template('tournaments.html', tournaments=rows)


@app.route('/plays-for', methods=['GET', 'POST'])
def plays_for():
    conn = get_db_connection()
    if request.method == 'POST':
        conn.execute(
            '''INSERT INTO plays_for (player_id, team_id, date_joined, date_left)
               VALUES (?, ?, ?, ?)''',
            (
                request.form['player_id'],
                request.form['team_id'],
                request.form['date_joined'] or None,
                request.form['date_left'] or None,
            ),
        )
        conn.commit()
        flash('Relationship added.')
        conn.close()
        return redirect(url_for('plays_for'))

    players = conn.execute(
        'SELECT player_id, name, username FROM players ORDER BY name'
    ).fetchall()
    teams = conn.execute(
        'SELECT team_id, name FROM teams ORDER BY name'
    ).fetchall()
    rows = conn.execute(
        '''SELECT pf.plays_for_id, p.name AS player_name, p.username, t.name AS team_name, pf.date_joined, pf.date_left
           FROM plays_for pf
           JOIN players p ON pf.player_id = p.player_id
           JOIN teams t ON pf.team_id = t.team_id
           ORDER BY pf.plays_for_id DESC'''
    ).fetchall()
    conn.close()
    return render_template('plays_for.html', players=players, teams=teams, rows=rows)


@app.route('/played-in', methods=['GET', 'POST'])
def played_in():
    conn = get_db_connection()
    if request.method == 'POST':
        conn.execute(
            '''INSERT INTO played_in (team_id, tournament_id, date_played)
               VALUES (?, ?, ?)''',
            (
                request.form['team_id'],
                request.form['tournament_id'],
                request.form['date_played'] or None,
            ),
        )
        conn.commit()
        flash('Appearance added.')
        conn.close()
        return redirect(url_for('played_in'))

    teams = conn.execute(
        'SELECT team_id, name FROM teams ORDER BY name'
    ).fetchall()
    tournaments = conn.execute(
        'SELECT tournament_id, name FROM tournaments ORDER BY name'
    ).fetchall()
    rows = conn.execute(
        '''SELECT pi.played_in_id, t.name AS team_name, tr.name AS tournament_name, pi.date_played
           FROM played_in pi
           JOIN teams t ON pi.team_id = t.team_id
           JOIN tournaments tr ON pi.tournament_id = tr.tournament_id
           ORDER BY pi.played_in_id DESC'''
    ).fetchall()
    conn.close()
    return render_template('played_in.html', teams=teams, tournaments=tournaments, rows=rows)


@app.route('/reports', methods=['GET', 'POST'])
def reports():
    conn = get_db_connection()

    teammates = []
    selected_player = None

    if request.method == 'POST':
        selected_player = request.form['player_name']

        teammates = conn.execute(
            '''SELECT DISTINCT p2.name, p2.username, t.name AS team_name
               FROM players p1
               JOIN plays_for pf1 ON p1.player_id = pf1.player_id
               JOIN plays_for pf2 ON pf1.team_id = pf2.team_id
               JOIN players p2 ON pf2.player_id = p2.player_id
               JOIN teams t ON pf1.team_id = t.team_id
               WHERE p1.name = ?
                 AND p2.player_id != p1.player_id'''
            , (selected_player,)
        ).fetchall()

    players_per_team = conn.execute(
        '''SELECT t.name AS team_name, COUNT(pf.player_id) AS player_count
           FROM teams t
           LEFT JOIN plays_for pf ON t.team_id = pf.team_id
           GROUP BY t.team_id, t.name
           ORDER BY player_count DESC, t.name'''
    ).fetchall()

    tournaments_per_team = conn.execute(
        '''SELECT t.name AS team_name, COUNT(pi.tournament_id) AS tournament_count
           FROM teams t
           LEFT JOIN played_in pi ON t.team_id = pi.team_id
           GROUP BY t.team_id, t.name
           ORDER BY tournament_count DESC, t.name'''
    ).fetchall()

    high_prize_tournaments = conn.execute(
        '''SELECT name, country, prize_pool
           FROM tournaments
           WHERE prize_pool >= 500000
           ORDER BY prize_pool DESC'''
    ).fetchall()

    players = conn.execute(
        'SELECT name FROM players ORDER BY name'
    ).fetchall()

    conn.close()

    return render_template(
        'reports.html',
        players_per_team=players_per_team,
        tournaments_per_team=tournaments_per_team,
        high_prize_tournaments=high_prize_tournaments,
        teammates=teammates,
        players=players,
        selected_player=selected_player
    )


if __name__ == '__main__':
    if not DATABASE.exists():
        init_db()
        seed_db()
    app.run(debug=True)