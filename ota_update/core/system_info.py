import time
import socket
import psutil

def get_system_info():
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
