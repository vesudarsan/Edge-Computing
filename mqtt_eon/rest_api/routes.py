from flask import Flask, request, jsonify
from utils.logger import setup_logger

logging = setup_logger(__name__)



# ------------------------
# Flask Routes
# ------------------------
def register_routes(app,publisher,buffer):
    @app.get("/")
    def root():
        return jsonify({"status": "ok"})

    @app.post("/start")
    def start():
        if publisher.running:
            return jsonify({"status": "already running"}), 400
        success = publisher.start()
        return jsonify({"status": "started" if success else "failed"}), 200 if success else 500

   
    @app.post("/stop")
    def stop():
        if publisher.stop():
            return jsonify({"status": "stopped"}), 200
        return jsonify({"status": "not running"}), 400

   
    @app.get("/status")
    def status():
        return jsonify({"running": publisher.running, "mqtt_connected": publisher.mqtt_connected})

   
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})


  
    @app.get("/buffer/status")
    def buffer_status():
        result = buffer.getBufferCount()
        if "error" in result:
            return jsonify(result), result.get("code", 500)
        return jsonify(result)
    

   
    @app.post("/publish")
    def publish_message():
        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({"error": "Missing 'message' in request body"}), 400

        topic = data.get('topic', publisher.topic)  # optional override
        message = data['message']

        if publisher.is_mqtt_connected():
            result = publisher.client.publish(topic,message)
         
            if result and getattr(result, "rc", 1) == 0:   
                logging.info(f"Payload: {message}, topic: {topic}")
                
                return jsonify({"status": "published", "topic": topic}), 200
            else:
                # MQTT connected but publish failed — buffer it                
               
                publisher.store_payload(data)
                return jsonify({"status": "publish failed, buffered", "topic": topic}), 202
        else:
            # MQTT not connected — buffer it
            publisher.store_payload(data)

            return jsonify({"status": "mqtt disconnected, buffered", "topic": topic}), 202
        

    # @app.route('/drone/servo', methods=['POST'])
    # def set_servo():
    #     """
    #     Set servo output (PWM)
    #     Input: { "servo_channel": 9, "pwm": 1500 }
    #     """
    #     try:
    #         data = request.get_json()
    #         channel = int(data["servo_channel"])
    #         pwm = int(data["pwm"])

    #         # publisher.connection.mav.command_long_send(
    #         #     publisher.connection.target_system,
    #         #     publisher.connection.target_component,
    #         #     mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
    #         #     0,
    #         #     channel,
    #         #     pwm,
    #         #     0, 0, 0, 0, 0
    #         # )
    #         return jsonify({"status": "servo command sent", "channel": channel, "pwm": pwm}), 200
    #     except Exception as e:
    #         logging.error(f"Set servo failed: {e}")
    #         return jsonify({"error": str(e)}), 500


    # @app.route('/drone/relay', methods=['POST'])
    # def set_relay():
    #     """
    #     Set digital relay output
    #     Input: { "relay_number": 0, "state": 1 }
    #     """
    #     try:
    #         data = request.get_json()
    #         relay_num = int(data["relay_number"])
    #         state = int(data["state"])  # 1 for ON, 0 for OFF

    #         # publisher.connection.mav.command_long_send(
    #         #     publisher.connection.target_system,
    #         #     publisher.connection.target_component,
    #         #     mavutil.mavlink.MAV_CMD_DO_SET_RELAY,
    #         #     0,
    #         #     relay_num,
    #         #     state,
    #         #     0, 0, 0, 0, 0
    #         # )
    #         return jsonify({"status": "relay command sent", "relay": relay_num, "state": state}), 200
    #     except Exception as e:
    #         logging.error(f"Set relay failed: {e}")
    #         return jsonify({"error": str(e)}), 500


    # @app.route('/drone/pwm', methods=['POST'])
    # def set_pwm():
    #     """
    #     Set raw PWM output on an actuator
    #     Input: { "output": 10, "pwm": 1600 }
    #     """
    #     try:
    #         data = request.get_json()
    #         output = int(data["output"])
    #         pwm = int(data["pwm"])

    #         # publisher.connection.mav.command_long_send(
    #         #     publisher.connection.target_system,
    #         #     publisher.connection.target_component,
    #         #     mavutil.mavlink.MAV_CMD_DO_SET_PWM,
    #         #     0,
    #         #     output,  # Output number
    #         #     pwm,     # PWM value
    #         #     0, 0, 0, 0, 0
    #         # )
    #         return jsonify({"status": "pwm command sent", "output": output, "pwm": pwm}), 200
    #     except Exception as e:
    #         logging.error(f"Set PWM failed: {e}")
    #         return jsonify({"error": str(e)}), 500