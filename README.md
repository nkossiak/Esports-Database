# Competitive Esports Network - Phase II Prototype

 Prototype for the Intro Databases project using **Python + Flask + SQLite**.

## Progress
- `players`, `teams`, and `tournaments` tables
- relationship tables: `plays_for` and `played_in`
- basic web pages to:
  - add players
  - add teams
  - add tournaments
  - add `Plays For` records
  - add `Played In` records
- simple report queries
- starter seed data

## Project structure
- `app.py` -> Flask app and routes
- `schema.sql` -> SQLite schema
- `templates/` -> HTML pages
- `requirements.txt` -> dependency list

## Run it
1. Open terminal in this folder.
2. Install requirements:
   - `pip install -r requirements.txt`
3. Run the app:
   - `python app.py`
4. Open in browser:
   - `http://127.0.0.1:5000`

## Reset the database
Delete `esports.db`.
