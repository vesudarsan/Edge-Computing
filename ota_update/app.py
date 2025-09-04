from utils.db import init_db
import json
from flask import Flask
from rest_api.routes import register_routes

from utils.logger import setup_logger
log = setup_logger()

app = Flask(__name__)

# Load config
CONFIG_PATH = "config.json"
try:
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
        FLASK_PORT = config.get("flask_port", 5000)
except:
    FLASK_PORT = 5000


# Register REST API routes
register_routes(app)    

if __name__ == "__main__":
    init_db()
    log.info("🚀 Starting Edge Compute OTA Agent REST services...v1.0")
    app.run(host="0.0.0.0", port=FLASK_PORT, threaded=True)