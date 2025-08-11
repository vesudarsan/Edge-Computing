import sqlite3
import platform
from flask import jsonify
from utils.logger import setup_logger
logging = setup_logger(__name__)

class DBBuffer:
    def __init__(self, path="buffer.db"):  
        if platform.system() == "Windows": 
            self.path = "buffer.db"
        else:
            self.path = "/app/data/buffer.db"
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS buffer (id INTEGER PRIMARY KEY, payload TEXT)")

    def store_payload(self, payload):
       
        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO buffer (payload) VALUES (?)", (str(payload),))     
            logging.info("💾 Stored offline payload.")     

    def getAllRows(self):
        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, payload FROM buffer ORDER BY id ASC")
            rows = cursor.fetchall()
            return rows

    def delete(self, row_id):
        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM buffer WHERE id = ?", (row_id,))
        
    def getBufferCount(self):
        with sqlite3.connect(self.path) as conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM buffer")
                count = cursor.fetchone()[0]
                return {"buffered_messages": count}
            except Exception as e:
                logging.error(f"Buffer status error: {e}")
                return {"error": "Could not retrieve buffer status"}, 500


    def clear_all(self):
        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM buffer")
            logging.info("🗑️ Cleared all buffered data.")