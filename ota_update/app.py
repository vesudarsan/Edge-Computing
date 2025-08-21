from utils.db import init_db
from rest_api.routes import app
import json

from utils.logger import setup_logger
log = setup_logger()

# Load config
CONFIG_PATH = "config.json"
try:
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
        FLASK_PORT = config.get("flask_port", 5000)
except:
    FLASK_PORT = 5000

if __name__ == "__main__":
    init_db()
    log.info("🚀 Starting Edge Compute OTA Agent REST services...")
    app.run(host="0.0.0.0", port=FLASK_PORT, threaded=True)