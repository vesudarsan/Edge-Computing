import paho.mqtt.client as mqtt
import json
import time
import psutil
import socket
import platform
from utils.logger import setup_logger
from utils.rest_client import RestClient
logging = setup_logger(__name__)

class MQTTClient:
    def __init__(self, broker, port, topic,drone_id,sparkplug_namespace,
                            sp_group_id,sp_edge_id,sp_device_id):       
        self.client = mqtt.Client(client_id=str(drone_id), clean_session=True)
        self.broker = broker
        self.port = port
        self.topic = topic
        self.connected = False

        self.drone_id = drone_id
        self.sparkplug_namespace = sparkplug_namespace
        self.sp_group_id = sp_group_id
        self.sp_edge_id = sp_edge_id
        self.sp_device_id = sp_device_id
        self.TOPIC_PREFIX = f"{sparkplug_namespace}/{sp_group_id}/+/{sp_edge_id}"
        self.rest_client = RestClient()

 

    def connect(self,topic,lwt_message,qos=1,retain=True):
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.will_set(topic,lwt_message,qos,retain)        
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

    def disconnect(self):
        disconnect_msg = json.dumps({
            "drone_id": self.drone_id,
            "status": "disconnect",
            "start_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })

        topic = f"{self.sparkplug_namespace}/{self.sp_group_id}/NDEATH/{self.sp_edge_id}"
        self.client.publish(topic, payload=disconnect_msg, qos=1, retain=True)

        try:
            self.client.loop_stop()
            self.client.disconnect()
        finally:
            self.connected = False
            logging.info("✅ MQTT disconnected")


    def get_system_info(self):
        hostname = socket.gethostname()
        try:
            ip_address = socket.gethostbyname(hostname)
        except:
            ip_address = "unknown"
        uptime = time.time() - psutil.boot_time()
        cpu_percent = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        return {
            "hostname": hostname,
            "ip_address": ip_address,
            "uptime_seconds": round(uptime),
            "cpu_percent": cpu_percent,
            "memory": {
                "total_mb": round(mem.total / 1024 / 1024),
                "used_mb": round(mem.used / 1024 / 1024),
                "percent": mem.percent
            }
        }

    def publish_birth_message(self):        

        birth_msg = json.dumps({
            "drone_id": self.drone_id,
            "status": "online",
            "start_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "system": self.get_system_info(),
            # "deployments": get_deployments()
        })

        topic = f"{self.sparkplug_namespace}/{self.sp_group_id}/NBIRTH/{self.sp_edge_id}"
        self.client.publish(topic, payload=birth_msg, qos=1, retain=True)

        logging.info("Published MQTT birth message")        

    def _on_connect(self, client, userdata, flags, rc):
        self.connected = (rc == 0)

        if self.connected:            
            logging.info(f"✅ Connected to MQTT broker [{self.broker}:{self.port}] with code {rc}")
        else:           
            logging.error(f"❌ Failed to connect to MQTT broker [{self.broker}:{self.port}] with code {rc}")
            return

        # Publish NBIRTH (only if Sparkplug fields exist)
        try:
            self.publish_birth_message()
        except Exception as e:
            logging.error(f"⚠️ Failed to publish NBIRTH: {e}")

        # Define topics to subscribe
        topics = [
           # f"{self.sparkplug_namespace}/{self.sp_group_id}/+/+/#",  # wildcard for Sparkplug messages
            f"{self.TOPIC_PREFIX}/deploy",
            f"{self.TOPIC_PREFIX}/start",
            f"{self.TOPIC_PREFIX}/stop",
            f"{self.TOPIC_PREFIX}/restart",
            f"{self.TOPIC_PREFIX}/health",
            f"{self.TOPIC_PREFIX}/status",
            f"{self.TOPIC_PREFIX}/containers",
            f"{self.sparkplug_namespace}/{self.sp_group_id}/NCMD/{self.sp_edge_id}/",
            f"{self.sparkplug_namespace}/{self.sp_group_id}/DCMD/{self.sp_edge_id}/MAVLINK"
        ]

        # Subscribe and log each topic
        for t in topics:
            try:
                client.subscribe(t)
                logging.info(f"📡 Subscribed to topic: {t}")
            except Exception as e:
                logging.error(f"⚠️ Failed to subscribe to {t}: {e}")
  
    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        logging.warning("❌ MQTT disconnected")

    def subscribe(self, topic):
        self.client.client.subscribe(topic)
        self.client.client.on_message = self._on_message

    def _on_message(self, client, userdata, msg):
               
        try:
            payload_str = msg.payload.decode("utf-8")
            logging.info(f"📩 Received message on {msg.topic}: {payload_str}")

            # Only process messages for MAVLINK topics      
            if "MAVLINK" not in msg.topic.upper():
                logging.info("⏭ Skipping message (not a MAVLINK topic)")
                return

            data = json.loads(payload_str)

            if data.get("CMD") == "BIN_FILE":
                logging.info("📂 Command received to send BIN_FILE.")

                # Call your BIN file upload logic here
                # Call the MAVLink REST service
                if platform.system() == "Windows": 
                    url = "http://localhost:5002/drone/readSendBinFile" # 2dl read from config
                else:
                    url = "http://mavlink-service:5002/drone/readSendBinFile"  # 2dl read from config

                self.rest_client.post(url, data)

        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in payload: {e}")
        except Exception as e:
            logging.error(f"Error processing message: {e}")




    def publish(self, topic=None, payload =None, qos=1,storeAndForward = False):   
        actual_topic = topic or self.topic
        if not self.connected:
            logging.warning("❌ MQTT not connected")
            return None
        
        logging.info(f"✅ Published to {actual_topic} [qos={qos}]")
        return self.client.publish(actual_topic, payload, qos=qos)



    def is_connected(self):
        return self.connected