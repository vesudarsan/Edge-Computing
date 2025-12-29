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
from datetime import datetime, timezone
from pymavlink import mavutil
from utils.rest_client import RestClient
from rest_api.routes import register_routes

from utils.logger import setup_logger
logging = setup_logger(__name__)

app = Flask(__name__)   


ALLOWED_MAVLINK_MSGS = {
    "ATTITUDE",
    "GLOBAL_POSITION_INT",
    "HEARTBEAT",
    "SYS_STATUS",
    "SERVO_OUTPUT_RAW",
    "RC_CHANNELS",
    "SYSTEM_TIME",
    "BATTERY_STATUS",
    "MCU_STATUS",
    "MISSION_CURRENT",
    "FENCE_STATUS",
    "VIBRATION"
}

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
            self.mqtt_eon_rest_call = RestClient("http://localhost:5001/")# 2dl read from config
        else:
            self.mqtt_eon_rest_call = RestClient("http://mqtt-eon-service:5001/")# 2dl read from config
      
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
        # --- Flight time tracking ---
        self.armed = False
        self.flight_start_ts = None      # epoch seconds when arming starts
        self.total_flight_seconds = 0.0  # cumulative in this process lifetime
        self.last_flight_metric_ts = 0.0
        self.flight_metric_topic = f"{SPARKPLUG_NAMESPACE}/{SP_GROUP_ID}/DDATA/{SP_EDGE_ID}/FlightMetrics"
        self.bin_file_topic = f"{SPARKPLUG_NAMESPACE}/{SP_GROUP_ID}/DDATA/{SP_EDGE_ID}/binFile"


        
 

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
    
    def _on_armed(self):
        self.armed = True
        self.flight_start_ts = time.time()
        logging.info(f"🟢 ARMED at {datetime.utcnow().isoformat()}Z")

    def _on_disarmed(self):
        # close the current armed window
        if self.armed and self.flight_start_ts:
            delta = time.time() - self.flight_start_ts
            self.total_flight_seconds += max(0.0, delta)
            logging.info(f"🔴 DISARMED at {datetime.utcnow().isoformat()}Z | "
                        f"+{delta:.1f}s this flight | "
                        f"Total: {self.total_flight_seconds:.1f}s")
        self.armed = False
        self.flight_start_ts = None

    def get_flight_time_seconds(self) -> float:
        """Total accumulated seconds, including an in-progress armed window."""
        total = self.total_flight_seconds
        if self.armed and self.flight_start_ts:
            total += max(0.0, time.time() - self.flight_start_ts)
        return total

    def get_flight_time_hours(self) -> float:
        return self.get_flight_time_seconds() / 3600.0

    
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
            # if msg_type not in ALLOWED_MAVLINK_MSGS: # 2dl allowing all mavlink msgs for now, no filters applied 
            #     logging.debug(f"❌ Ignored MAVLink message: {msg_type}")
            #     return None # Ignore unlisted messages
            
            if msg.get_type() == "HEARTBEAT":
                self.last_heartbeat_time = time.time()

            data["messageType"] = msg_type
            for field in msg.get_fieldnames():
                data[field] = getattr(msg, field)

            # Add timestamp in RFC3339 UTC format
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
            # Or, if you prefer epoch nanoseconds for InfluxDB         
            # data["timestamp_ns"] = int(time.time() * 1_000_000_000)

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
        # finalize an open armed session
        if self.armed:
            self._on_disarmed()
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
            logging.info(f"Polling MAVLink...... v1.0.0") 
           
            try:
                msg = self.connection.recv_match(blocking=True, timeout=5)
                # print("MAVLINK MSG:",msg)
             
                if msg:
                    data = self.decode_msgs(msg)
                    if data:
                        # --- Detect ARM/DISARM from HEARTBEAT ---
                        if data.get("messageType") == "HEARTBEAT":
                            print("HEARTBEAT message received")
                            base_mode = data.get("base_mode")
                            if base_mode is not None:
                                currently_armed = (base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0
                                if currently_armed and not self.armed:
                                    self._on_armed()
                                elif (not currently_armed) and self.armed:
                                    self._on_disarmed()



                        payload = {"topic": self.topic,"message": str(data)}

                        self.mqtt_eon_rest_call.publish(payload)


                        # Throttle a separate metric publish (~5s)
                        
                        now = time.time()
                        # print("now:",now)
                        # print("last_flight_metric_ts:",self.last_flight_metric_ts)
                    
                        # print("now - self.last_flight_metric_ts", now - self.last_flight_metric_ts)
                        if now - self.last_flight_metric_ts >= 5.0:
                            self.last_flight_metric_ts = now
                          
                            metric = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "armed": self.armed,
                                "flight_time_seconds": round(self.get_flight_time_seconds(), 1),
                                "flight_time_hours": round(self.get_flight_time_hours(), 3),
                            }
                            # self.mqtt_eon_rest_call.publish({
                            #     "topic": self.flight_metric_topic,
                            #     "message": json.dumps(metric)
                            # })
                            # print("topic:",self.flight_metric_topic)
                            # print("Published flight metrics:", metric)

     
                        # try:
                        #     if requests.get 
                        #     response = requests.post(self.url+"publish", json=payload, timeout=5)
                        #     if response.status_code == 200:
                        #         logging.info(f"✅ Published successfully:{response.json()}" )
                        #         # print("✅ Published successfully:", response.json())
                        #     elif response.status_code == 202:
                        #         logging.info(f"⚠️ Buffered:{response.json()}" )
                        #         # print("⚠️ Buffered:", response.json())
                        #     else:
                        #         logging.info(f"❌ Failed ({response.status_code},{response.text}):" )
                        #         # print(f"❌ Failed ({response.status_code}):", response.text)

                        # except requests.exceptions.RequestException as e:
                        #     logging.error(f"Error connecting to REST API:", e)
                        #     # print("Error connecting to REST API:", e)
                    else:
                        logging.debug("Filtered message.")
                else:
                    logging.debug("No message this cycle.")
            except Exception as e:
                logging.error(f"Error in run_loop: {e}")
            time.sleep(3.0)  # Polling interval    

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
        # self.connection.mav.command_long_send(self.connection.target_system,
        #                                        self.connection.target_component,
        #                                        mavutil.mavlink.MAV_CMD_LOG_REQUEST_LIST, 0,
        #                                        0, 0xFFFFFFFF, 0, 0, 0, 0, 0)
        self.connection.mav.command_long_send(
                                                self.connection.target_system,
                                                self.connection.target_component,
                                                117,  # MAV_CMD_LOG_REQUEST_LIST
                                                0,
                                                0, 0xFFFFFFFF, 0, 0, 0, 0, 0
                                            )

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


            # Publish to MQTT
        try:
            self.mqtt_eon_rest_call.publish(
                {"topic": self.bin_file_topic, "message": json.dumps(payload)}
            )
            logging.info(f"Published MQTT payload for {file_path}")
        except Exception as e:
            logging.error(f"MQTT publish failed: {e}")
            return {"status": "error", "message": str(e)}

        # Return REST response
        return {"status": "success", "file": file_path, "flight_id": payload["flight_id"]}

           
 

    def readSendBinFile(self):     
        if self.is_disarmed(): 
            logging.info(f"Disarm detected")            
            log_id = self.get_latest_log_filename()
            if log_id is not None:
                file_path = f"log_{log_id}.bin"
                self.download_log(self.connection, log_id, file_path)
                return self.send_file_to_mqtt(file_path) # must return a Flask-valid response
            else:
                logging.info(f"No logs found")
                # Publish MQTT notification too
                payload = {"topic": self.bin_file_topic, "message": "No logs found"}
                self.mqtt_eon_rest_call.publish(payload)

                return {"status": "no_logs"}, 404   # <-- return a valid response
        else:
            logging.info(f"Still armed, waiting...")
            payload = {"topic": self.bin_file_topic, "message": "Still armed, waiting..."}
            self.mqtt_eon_rest_call.publish(payload)

            return {"status": "armed"}, 200  # <-- return a valid response
          


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