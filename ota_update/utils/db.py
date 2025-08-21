import sqlite3

DB_FILE = "deployments.db"

def init_db():
    with sqlite3.connect(DB_FILE, check_same_thread=False) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                image TEXT NOT NULL,
                version TEXT NOT NULL,
                ports TEXT NOT NULL,
                container_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

def save_deployment(name, image, version, ports_json, container_id):
    with sqlite3.connect(DB_FILE, check_same_thread=False) as conn:
        conn.execute('''
            INSERT INTO deployments (name, image, version, ports, container_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, image, version, ports_json, container_id))
        conn.commit()

def load_deployments():
    with sqlite3.connect(DB_FILE, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, image, version, ports, container_id, timestamp FROM deployments")
        return cursor.fetchall()
