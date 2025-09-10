import signal, sys, json, os,time, threading
from flask import Flask, request, jsonify
from core.mqttClient import MQTTClient
from utils.db_buffer import DBBuffer
from core.mqtt_publisher import MQTTPublisher
from rest_api.routes import register_routes


from utils.logger import setup_logger
logging = setup_logger(__name__)

app = Flask(__name__)


# Load config
CFG_PATH = "config/config.json"

try: 
     with open(CFG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)    
        MQTT_BROKER = config["mqtt_broker"]
        MQTT_PORT = config["mqtt_port"]
        TOPIC = config["topic"]  
        DRONE_UID = config["drone_UID"]

        SPARKPLUG_NAMESPACE = config["sparkplug_namespace"]
        SP_GROUP_ID = config["sparkplug_group_id"]
        SP_EDGE_ID = config["drone_UID"]
        SP_DEVICE_ID = config["sparkplug_device_id"]

        logging.info(f" [✅] Loaded  config values from file")

except FileNotFoundError:    
    logging.error(f"❌ Config file not found '{config/config.json}'. Using default config values.")    
    MQTT_BROKER = "test.mosquitto.org"
    MQTT_PORT = 1883
    TOPIC = "mydrone/sensors"
    DRONE_UID = "123456789"
    # Sparkplug-like MQTT structure using JSON payloads
    SPARKPLUG_NAMESPACE = "spBv1.0"
    SP_GROUP_ID = "DroneFleet"
    SP_EDGE_ID = "DHAKSHA-001"        # e.g., DRONE-001
    SP_DEVICE_ID = ""            # Optional


buffer = DBBuffer()

# ------------------------
# Instantiate Publisher
# ------------------------
publisher = MQTTPublisher(MQTT_BROKER,MQTT_PORT,TOPIC,DRONE_UID,buffer,SPARKPLUG_NAMESPACE,
                                SP_GROUP_ID,SP_EDGE_ID,SP_DEVICE_ID)

# Register REST API routes
register_routes(app, publisher,buffer)

TOPIC_PREFIX = f"{SPARKPLUG_NAMESPACE}/{SP_GROUP_ID}/+/{SP_EDGE_ID}"

# ------------------------
# Graceful Shutdown on Ctrl+C
# ------------------------
def handle_shutdown(sig, frame):
    logging.info("🛑 Ctrl+C detected. Shutting down...")
    publisher.stop()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_shutdown)
    logging.info("🔌 Starting MQTT Publisher client services")
    publisher.start()
    logging.info("🚀 Starting Flask service on port 5001")
    app.run(host="0.0.0.0", port=5001)




