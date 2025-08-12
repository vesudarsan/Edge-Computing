import signal
import sys
import os
import platform
from flask import Flask, request, jsonify
import time
import threading
import json
import requests
import base64
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
        DRONE_UID = config["drone_UID"]

        SPARKPLUG_NAMESPACE = config["sparkplug_namespace"]
        SP_GROUP_ID = config["sparkplug_group_id"]
        SP_EDGE_ID = config["drone_UID"]
        SP_DEVICE_ID = config["sparkplug_device_id"]

        logging.info(f" [✅] Loaded  config values from file")

except FileNotFoundError:    
    logging.error(f"❌ Config file not found '{config/config.json}'. Using default config values.")    
    MAVLINK_CONN_STR = "udp:0.0.0.0:14550"
    COM_TYPE = "udp"
    COM_NUMBER = "COM12"
    BAUD_RATE = 115200
    DRONE_UID = "123456789"

    SPARKPLUG_NAMESPACE = "spBv1.0"
    SP_GROUP_ID = "DroneFleet"
    SP_EDGE_ID = "DHAKSHA-001"        # e.g., DRONE-001
    SP_DEVICE_ID = ""            # Optional


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
        self.deviceId = "Mavlink"
        self.topic = f"{SPARKPLUG_NAMESPACE}/{SP_GROUP_ID}/DDATA/{SP_EDGE_ID}/{self.deviceId}"
 

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
    

    def run_loop(self):     
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

    def is_disarmed(self):
        self.connection.mav.request_data_stream_send(self.connection.target_system, self.connection.target_component,
                                            mavutil.mavlink.MAV_DATA_STREAM_ALL, 1, 1)
        msg = self.connection.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
        if msg:
            base_mode = msg.base_mode
            # Check if disarmed (ARMED bit unset)
            return (base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) == 0
        return False


    def get_latest_log_filename(self):
        self.connection.mav.command_long_send(self.connection.target_system, self.connection.target_component,
                                  mavutil.mavlink.MAV_CMD_LOG_REQUEST_LIST, 0,
                                  0, 0xFFFFFFFF, 0, 0, 0, 0, 0)
        logs = []
        while True:
            msg = self.connection.recv_match(type='LOG_ENTRY', blocking=True, timeout=3)
            if not msg:
                break
            logs.append((msg.num_logs, msg.last_log_num))

        if logs:
            return logs[-1][1]  # latest log num
        return None

    def download_log(master, log_id, file_path):
        logging.info(f"Requesting log {log_id} download")
      
        master.mav.log_request_data_send(master.target_system, master.target_component,
                                        log_id, 0, 90)
        with open(file_path, 'wb') as f:
            while True:
                msg = master.recv_match(type='LOG_DATA', blocking=True, timeout=5)
                if not msg:
                    break
                f.write(msg.data[:msg.count])
                if msg.ofs + msg.count >= msg.size:
                    break
        logging.info(f"Log downloaded to {file_path}")
       

    def send_file_to_mqtt(self,file_path):

        if not os.path.exists(file_path):
            logging.info(f"[ERROR] File not found: {file_path}")        
            return

        with open(file_path, "rb") as f:
            binary_data = f.read()
            encoded_data = base64.b64encode(binary_data).decode('utf-8')  # Convert to string

        payload = {
            "flight_id": f"flight_{int(time.time())}",
            "filename": os.path.basename(file_path),
            "timestamp": time.time(),
            "bin_file_base64": encoded_data
        }

        return json.dumps(payload)
    
 

    def readSendBinFile(self):
        print("1111111")#2dl need to test with real cube and confirm
        if self.is_disarmed(): 
            logging.info(f"Disarm detected")
            log_id = self.get_latest_log_filename(self.connection)
            if log_id is not None:
                file_path = f"log_{log_id}.bin"
                self.download_log(self.connection, log_id, file_path)
                return self.send_file_to_mqtt(file_path)
            else:
                logging.info(f"No logs found")
        else:
            logging.info(f"Still armed, waiting...")
          

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