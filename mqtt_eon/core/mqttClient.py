import paho.mqtt.client as mqtt
import json
import time
import psutil
import socket
from utils.logger import setup_logger
logging = setup_logger(__name__)

class MQTTClient:
    def __init__(self, broker, port, topic,drone_id,sparkplug_namespace,
                            sp_group_id,sp_edge_id,sp_device_id):
        self.client = mqtt.Client(drone_id)
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

    def connect(self,topic,lwt_message,qos=1,retain=True):
        self.client.on_connect = self._on_connect
        self.client.will_set(topic,lwt_message,qos,retain)
        self.client.on_disconnect = self._on_disconnect
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

        self.client.loop_stop()
        self.client.disconnect()
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

        logging.info(f"✅ Connected to MQTT broker.[{self.broker}] with code {rc}")  
        self.connected = True  
        # Publish NBIRTH message
        self.publish_birth_message()
        client.subscribe(f"{self.sparkplug_namespace}/{self.sp_group_id}/+/+/#")

        client.subscribe(f"{self.TOPIC_PREFIX}/deploy")
        client.subscribe(f"{self.TOPIC_PREFIX}/start")
        client.subscribe(f"{self.TOPIC_PREFIX}/stop")
        client.subscribe(f"{self.TOPIC_PREFIX}/restart")
        client.subscribe(f"{self.TOPIC_PREFIX}/health")
        client.subscribe(f"{self.TOPIC_PREFIX}/status")
        client.subscribe(f"{self.TOPIC_PREFIX}/containers")

        # Subscribe to NCMD and DCMD topics
        client.subscribe(f"{self.sparkplug_namespace}/{self.sp_group_id}/NCMD/{self.sp_edge_id}")
        client.subscribe(f"{self.sparkplug_namespace}/{self.sp_group_id}/DCMD/{self.sp_edge_id}/{self.sp_device_id}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        logging.warning("❌ MQTT disconnected")

    def subscribe(self, topic):
        self.client.client.subscribe(topic)
        self.client.client.on_message = self._on_message

    def _on_message(self, client, userdata, msg):
        logging.info(f"📩 Received message on {msg.topic}: {msg.payload.decode()}")

    def publish(self, topic=None, payload =None, qos=1,storeAndForward = False):   
        actual_topic = topic or self.topic
        if self.connected:
            result = self.client.publish(actual_topic, payload,qos=qos)
            logging.info(f"✅ Published to {actual_topic} [qos={qos}]")
            return result
        else:
            logging.warning("❌ MQTT not connected")
            return None

    def is_connected(self):
        return self.connected