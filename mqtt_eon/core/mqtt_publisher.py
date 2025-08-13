import signal
import sys
import os

from core.mqttClient import MQTTClient
from utils.db_buffer import DBBuffer
import json
import time
import threading
import ast

from utils.logger import setup_logger
logging = setup_logger(__name__)


# ------------------------
# Publisher Class
# ------------------------
class MQTTPublisher:
    def __init__(self, mqtt_broker, mqtt_port, topic, drone_uid,buffer,sparkplug_namespace,
                            sp_group_id,sp_edge_id,sp_device_id):
        self.broker = mqtt_broker
        self.port = mqtt_port
        self.topic = topic
        self.client = MQTTClient(mqtt_broker, mqtt_port, topic, drone_uid,sparkplug_namespace,
                            sp_group_id,sp_edge_id,sp_device_id)
        
        self.mqtt_connected = False
        self.thread = None
        self.running = False
        self.buffer = buffer
        self.sparkplug_namespace = sparkplug_namespace
        self.sp_group_id = sp_group_id
        self.sp_edge_id = sp_edge_id
        self.sp_device_id = sp_device_id
        self.drone_uid = drone_uid
  
    
    def store_payload(self, payload):        
        self.buffer.store_payload(payload)
   

    def flush_buffer(self, max_flush=10):
        try:
            rows= self.buffer.getAllRows()             
            for i, (row_id, payload) in enumerate(rows):
                if i >= max_flush:
                    break
                
                payload_dict = ast.literal_eval(payload)

                topic = payload_dict.get('topic', self.topic)  # optional override
              
                message = payload_dict['message']               
                result = self.client.publish(topic, message,1)
                
                if result.rc == 0:
                    self.buffer.delete(row_id)                    
                    logging.info(f"✅ Replayed: {payload}")
                else:
                    logging.warning("❌ Failed to publish buffered message.")
                    break
        except Exception as e:
            logging.error(f"Failed to flush buffer: {e}")


    def connect_mqtt_with_retries(self,max_retries=10, delay_seconds=1):
        attempt = 0
        # --- LWT Setup ---
        lwt_message = json.dumps({
            "drone_id": self.drone_uid,
            "status": "offline",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })
        
        while True:
            try:
                logging.info(f"Attempting to connect to MQTT broker ({self.broker}:{self.port})... [Attempt {attempt + 1}]")
                self.client.connect(f"{self.sparkplug_namespace}/{self.sp_group_id}/NDEATH/{self.sp_edge_id}", 
                                    lwt_message, 1, True)
                logging.info("MQTT connected successfully.")
                self.mqtt_connected = True
                break
            except Exception as e:
                attempt += 1
                logging.warning(f"MQTT connection failed: {e}")
                # if attempt >= max_retries:
                #     log.error("Max retries reached. Giving up.")
                #     raise e
                self.mqtt_connected = False
                time.sleep(delay_seconds)               

    def start(self):
        if self.running:
            logging.info("Already running.")
            return False
        try:          
            self.connect_mqtt_with_retries(5,1)
            self.running = True      
            self.thread = threading.Thread(target=self.run_loop, daemon=True)
            self.thread.start()            
            return True
        except Exception as e:
            logging.error(f"Start failed: {e}")
            return False

    def stop(self):
        if not self.running:
            logging.info("Not running.")
            return False
        self.running = False   
        if self.thread:
            self.thread.join(timeout=3)     
       
        self.client.disconnect()
        self.mqtt_connected = False
        logging.info("✅ Stopped cleanly.")
        return True
    
    def is_mqtt_connected(self):
        return self.mqtt_connected

    def run_loop(self):
        logging.info("Started run_loop() thread for store and forward messages.")
        while self.running:
            #logging.info(f"Checking for store and forward messages !!!!")   
            self.mqtt_connected = self.client.is_connected() 
                
            try:
                if self.mqtt_connected:
                    self.flush_buffer()
                    time.sleep(1.0)
            except Exception as e:
                logging.error(f"❌ Exception in run_loop: {e}", exc_info=True)