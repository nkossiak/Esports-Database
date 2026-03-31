DROP TABLE IF EXISTS played_in;
DROP TABLE IF EXISTS plays_for;
DROP TABLE IF EXISTS tournaments;
DROP TABLE IF EXISTS teams;
DROP TABLE IF EXISTS players;

CREATE TABLE players (
    player_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    country TEXT,
    birth_year INTEGER,
    first_year INTEGER
);

CREATE TABLE teams (
    team_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    game TEXT NOT NULL,
    location TEXT,
    founded_year INTEGER,
    ranking INTEGER
);

CREATE TABLE tournaments (
    tournament_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    country TEXT,
    founded_year INTEGER,
    ranking INTEGER,
    prize_pool REAL
);

CREATE TABLE plays_for (
    plays_for_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    date_joined TEXT,
    date_left TEXT,
    UNIQUE(player_id, team_id, date_joined),
    FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE
);

CREATE TABLE played_in (
    played_in_id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    tournament_id INTEGER NOT NULL,
    date_played TEXT,
    UNIQUE(team_id, tournament_id, date_played),
    FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE,
    FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id) ON DELETE CASCADE
);
