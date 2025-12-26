import json
import os
import platform

# def get_config_path():
#     if platform.system() == "Windows":
#         return r"D:\edgeCompute\config.json"
#     else:
#         return "/edgeCompute/config.json"

# CONFIG_PATH = get_config_path()
CONFIG_PATH = "/edgeCompute/config.json"
os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

DEFAULT_CONFIG = {
    "mqtt_broker": "",
    "mqtt_port": 8883,
    "topic": "",

    "sparkplug_namespace": "spBv1.0",
    "sparkplug_group_id": "",
    "sparkplug_device_id": "",

    "drone_UID": "",
    "log_level": "INFO",

    "comm_type": "udp",
    "com_number": "COM12",
    "baudrate": 115200,
    "mavlink_connection_str": "udp:0.0.0.0:14550"
}

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_CONFIG.copy()

    with open(CONFIG_PATH, "r") as f:
        data = json.load(f)

    return {**DEFAULT_CONFIG, **data}

# def save_config(data):
#     with open(CONFIG_PATH, "w") as f:
#         json.dump(data, f, indent=2)

def save_config(data):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)