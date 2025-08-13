import requests
from utils.logger import setup_logger

logging = setup_logger(__name__)

class RestClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/") + "/"

    def is_healthy(self, timeout=1):
        """Check if the /health endpoint is responding."""
        try:
            url = self.base_url + "health"
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                logging.debug(f"[REST] Health check passed for {url}")
                return True
            else:
                logging.warning(f"[REST] Health check failed: {resp.status_code} {resp.text}")
                return False
        except requests.RequestException as e:
            logging.error(f"[REST] Health check error: {e}")
            return False

    def publish(self, payload, timeout=5):
        """Publish message to /publish if healthy."""
        if not self.is_healthy():
            logging.warning("[REST] Endpoint unhealthy. Skipping publish.")
            return None
        
        try:
            url = self.base_url + "publish"
            resp = requests.post(url, json=payload, timeout=timeout)
            logging.info(f"[REST] Publish response: {resp.status_code} {resp.text}")
            return resp
        except requests.RequestException as e:
            logging.error(f"[REST] Publish error: {e}")
            return None
