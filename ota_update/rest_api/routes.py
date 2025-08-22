import threading
from flask import Flask, jsonify, request,send_from_directory
from core.docker_manager import get_deployments, deploy_container, start_container, stop_container, restart_container,get_containers
from core.system_info import get_system_info
from flask_cors import CORS


# ------------------------
# Flask Routes
# ------------------------
def register_routes(app):
    CORS(app)   # 👈 enables CORS for all routes
    @app.get("/health")
    def health():
        return jsonify({"status": "running", "system": get_system_info()})

    @app.get("/status")
    def status():
        return jsonify(get_deployments())

    @app.get("/containers")
    def list_containers():
        return jsonify(get_containers())

    @app.post("/deploy")
    def deploy():
        data = request.get_json()
        image, name = data.get("image"), data.get("name")
        ports = data.get("ports", {})
        version = data.get("version", "latest")
        threading.Thread(target=deploy_container, args=(image, name, ports, version)).start()
        return jsonify({"status": "deployment triggered"})

    @app.post("/start")
    def start():
        data = request.get_json()
        name = data.get("name")
        threading.Thread(target=start_container, args=(name,)).start()
        return jsonify({"status": f"start triggered for '{name}'"})

    @app.post("/stop")
    def stop():
        data = request.get_json()
        name = data.get("name")
        threading.Thread(target=stop_container, args=(name,)).start()
        return jsonify({"status": f"stop triggered for '{name}'"})



    @app.post("/restart")
    def restart():
        data = request.get_json()
        name = data.get("name")
        threading.Thread(target=restart_container, args=(name,)).start()
        return jsonify({"status": f"restart triggered for '{name}'"})



    @app.route("/containers.html")
    def serve_containers_page():
        return send_from_directory("static", "containers.html")

    @app.route("/index.html")
    def serve_index_page():
        return send_from_directory("static", "index.html")   


