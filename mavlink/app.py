import signal
import sys
import os
import platform
from flask import Flask, request, jsonify
import time
import threading
import json
import requests
from pymavlink import mavutil
from rest_api.routes import register_routes

from utils.logger import setup_logger
logging = setup_logger(__name__)

app = Flask(__name__)

try:
    with open("config/config.json") as f:
        config = json.load(f)    
        MAVLINK_CONN_STR = config["mavlink_connection_str"]
        COM_TYPE = config["comm_type"]
        COM_NUMBER = config["com_number"]
        BAUD_RATE = config["baudrate"]
        logging.info(f" [✅] Loaded  config values from file")

except FileNotFoundError:    
    logging.error(f"❌ Config file not found '{config/config.json}'. Using default config values.")    
    MAVLINK_CONN_STR = "udp:0.0.0.0:14550"
    COM_TYPE = "udp"
    COM_NUMBER = "COM12"
    BAUD_RATE = 115200


# ------------------------
# Publisher Class
# ------------------------
class Mavlink:
    def __init__(self):

        if platform.system() == "Windows": 
            self.url = "http://localhost:5001/"
        else:
            self.url = "http://mqtt-eon-service:5001/"
      
        self.mavlink_connection_str = MAVLINK_CONN_STR
       
        self.connection = None
        self.thread = None
        self.running = False
        self.last_heartbeat_time = None
        self.com_type = COM_TYPE
        self.com_number = COM_NUMBER
        self.baud_rate = BAUD_RATE
        self.udp = MAVLINK_CONN_STR
        self.topic = "spBv1.0/DumsDroneFleet"
     

    def wait_for_heartbeat(self, retries=10, delay=3):
        for attempt in range(1, retries + 1):
            try:
                logging.info(f"🔄 Waiting for MAVLink heartbeat (attempt {attempt}/{retries})...")
                self.connection.wait_heartbeat(timeout=delay)
                logging.info(f"✅ Heartbeat received from system {self.connection.target_system}, component {self.connection.target_component}")
                self.last_heartbeat_time = time.time()
                return True
            except Exception as e:
                logging.warning(f"⏳ Attempt {attempt} failed: {e}")
                time.sleep(1)
        raise TimeoutError("❌ Heartbeat not received after retries.")
    
    def connect_mavlink(self):
        try:
            logging.info("Connecting to MAVLink...")
            if self.com_type == "udp":
                self.connection = mavutil.mavlink_connection(self.mavlink_connection_str)
            else:
                self.connection = mavutil.mavlink_connection(self.com_number, self.baud_rate)
                #self.connection = mavutil.mavlink_connection('COM12', 115200)           
            self.wait_for_heartbeat(retries=10, delay=3)
            logging.info(f"✅ Heartbeat from system {self.connection.target_system}, component {self.connection.target_component}")

            # ✅ Request all MAVLink data streams at 5Hz
            self.connection.mav.request_data_stream_send(
                self.connection.target_system,
                self.connection.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                1,  # Hz
                1   # start streaming
            )


        except Exception as e:
            logging.error(f"MAVLink connection failed: {e}")
            raise    

    def decode_msgs(self, msg):
        try:
            data = {}
            msg_type = msg.get_type()
            if msg_type not in ["ATTITUDE", "GLOBAL_POSITION_INT", "HEARTBEAT","SYS_STATUS"
                                ,"SERVO_OUTPUT_RAW","RC_CHANNELS","SYSTEM_TIME","BATTERY_STATUS",
                                "MCU_STATUS","MISSION_CURRENT","FENCE_STATUS","VIBRATION"]:
                return None
            
            if msg.get_type() == "HEARTBEAT":
                self.last_heartbeat_time = time.time()

            data["messageType"] = msg_type
            for field in msg.get_fieldnames():
                data[field] = getattr(msg, field)
            return data
        except Exception as e:
            logging.error(f"Decode error: {e}")
            return None        
        
    def start(self):
        if self.running:
            logging.info("Already running.")
            return False
        try:
            self.connect_mavlink()
           
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
        if self.connection: 
            self.connection.close()
        self.thread.join()     
        logging.info("✅ Stopped cleanly.")
        return True        
    

    def run_loop(self): # 2dl need to update full function 
        logging.info("Started run_loop() thread for Mav Link services.") # 
        while self.running:
            logging.info(f"Polling MAVLink...... v1.0")
           
            try:
                msg = self.connection.recv_match(blocking=True, timeout=5)
             
                if msg:
                    data = self.decode_msgs(msg)
                    if data:

                        payload = {"topic": self.topic,"message": str(data)}
     
                        try:
                            response = requests.post(self.url+"publish", json=payload, timeout=5)
                            if response.status_code == 200:
                                print("✅ Published successfully:", response.json())
                            elif response.status_code == 202:
                                print("⚠️ Buffered:", response.json())
                            else:
                                print(f"❌ Failed ({response.status_code}):", response.text)

                        except requests.exceptions.RequestException as e:
                            print("Error connecting to REST API:", e)
                    else:
                        logging.debug("Filtered message.")
                else:
                    logging.debug("No message this cycle.")
            except Exception as e:
                logging.error(f"Error in run_loop: {e}")
            time.sleep(0.1)    


# ------------------------
# Graceful Shutdown on Ctrl+C
# ------------------------
def handle_shutdown(sig, frame):
    logging.info("🛑 Ctrl+C detected. Shutting down...")
    service.stop()
    sys.exit(0)


# ------------------------
# Instantiate service
# ------------------------
service = Mavlink()
# Register REST API routes
register_routes(app, service)

# ------------------------
# Run Flask App
# ------------------------
if __name__ == "__main__":


    signal.signal(signal.SIGINT, handle_shutdown)
    logging.info("🔌 Starting MAVLINK services")
    success = service.start()
    logging.info("🚀 Starting Flask service on port 5002")
    app.run(host="0.0.0.0", port=5002)