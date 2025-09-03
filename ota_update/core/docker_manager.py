import json
import docker
from datetime import datetime
from utils.db import save_deployment, load_deployments
import platform

from utils.logger import setup_logger
log = setup_logger()



# ------------------------
# Docker Setup
# ------------------------
# if platform.system() == "Windows":   
#     docker_client = docker.DockerClient(base_url='npipe:////./pipe/docker_engine')
# else:
#     docker_client = docker.DockerClient(base_url='unix:///var/run/docker.sock')

if platform.system() == "Windows":
    #import docker
    docker_client = docker.DockerClient(base_url='npipe:////./pipe/docker_engine')
else:
    docker_client = docker.from_env()


def get_container_stats(container_id):
    try:
        container = docker_client.containers.get(container_id)
        stats = container.stats(stream=False)

        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
        cpu_percent = (cpu_delta / system_delta) * len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1])) * 100.0 if system_delta > 0 else 0

        memory_usage = stats["memory_stats"].get("usage", 0)
        memory_limit = stats["memory_stats"].get("limit", 1)
        memory_percent = (memory_usage / memory_limit) * 100.0

        return {
            "cpu_percent": round(cpu_percent, 2),
            "memory_mb": round(memory_usage / 1024 / 1024, 2),
            "memory_percent": round(memory_percent, 2)
        }
    except:
        return None

def get_container_lifecycle(container_id):
    try:
        container = docker_client.containers.get(container_id)
        info = container.attrs
        created = info["Created"]
        started = info["State"].get("StartedAt")
        status = info["State"].get("Status", "unknown")

        uptime = 0
        if started and started.endswith("Z"):
            started_dt = datetime.strptime(started[:26] + "Z", "%Y-%m-%dT%H:%M:%S.%fZ")
            uptime = (datetime.utcnow() - started_dt).total_seconds()

        return {
            "created_at": created.split(".")[0].replace("T", " "),
            "started_at": started.split(".")[0].replace("T", " ") if started else None,
            "status": status,
            "uptime_seconds": int(uptime)
        }
    except:
        return {"status": "unknown", "uptime_seconds": 0}

def get_deployments():
    deployments = []
    for name, image, version, ports_json, container_id, timestamp in load_deployments():
        deployments.append({
            "name": name,
            "image": image,
            "version": version,
            "ports": json.loads(ports_json),
            "container_id": container_id,
            "timestamp": timestamp,
            "lifecycle": get_container_lifecycle(container_id),
            "stats": get_container_stats(container_id)
        })
    return deployments

# def deploy_container(image, name, ports, version):
#     docker_client.images.pull(image)
#     try:
#         container = docker_client.containers.get(name)
#         container.stop()
#         container.remove()
#     except docker.errors.NotFound:
#         pass

#     formatted_ports = {f"{internal}/tcp": external for internal, external in ports.items()}
#     container = docker_client.containers.run(image, name=name, detach=True,
#                                              restart_policy={"Name": "always"},
#                                              ports=formatted_ports)

#     save_deployment(name, image, version, json.dumps(ports), container.id)
#     return container


def free_port(port_number):
    """Stop and remove any container using the given external port."""
    for c in docker_client.containers.list(all=True):
        ports = c.attrs["HostConfig"].get("PortBindings", {})
        for internal, binding in ports.items():
            for b in binding:
                if b.get("HostPort") == str(port_number):
                    log.warning(f"Port {port_number} is already used by container {c.name}. Removing it...")
                    try:
                        c.stop()
                        c.remove(force=True)
                        log.info(f"Released port {port_number} from container {c.name}")
                    except Exception as e:
                        log.error(f"Failed to remove container {c.name}: {e}")

def ensure_network(network_name="edgecompute-net"):
    for net in docker_client.networks.list():
        # if net.name == network_name or net.name.endswith(network_name):
        #     print("net.name", net.name)#2dl 
        #     return net.name # 2dl only for testing
        #     #return net
        if net.name.endswith(network_name):
           log.info(f"net.name {net.name}")
               
           return net.name # 2dl only for testing
                    #return net        
    return docker_client.networks.create(network_name, driver="bridge")
    # try:
    #     return docker_client.networks.get(network_name)
    # except docker.errors.NotFound:
    #     return docker_client.networks.create(network_name, driver="bridge")


# ------------------------
# Container Action Handlers
# ------------------------
def deploy_container(image, container_name,port_mappings,version):
    log.info(f"Starting deployment: {image} -> {container_name}")


    try:

        network = ensure_network("edgecompute-net")

        docker_client.images.pull(image)
        try:
            old = docker_client.containers.get(container_name)
            log.info(f"Stopping and removing existing container: {container_name}")
            old.stop()
            #container.remove()
            old.remove(force=True)
        except docker.errors.NotFound:
            log.info(f"No existing container named {container_name}")

        # Free all external ports that we are about to bind
        # for _, external in port_mappings.items():
        #     free_port(external)
        
        # formatted_ports = {f"{internal}/tcp": external for internal, external in port_mappings.items()}
        # print("formatted_ports", formatted_ports)  
        formatted_ports = {}
        for internal, external in port_mappings.items():
            if "/" in str(external):   # e.g. "14550/udp"
                external_port, proto = str(external).split("/")
                formatted_ports[f"{internal}/{proto}"] = int(external_port)
            else:
                formatted_ports[f"{internal}/tcp"] = int(external)
        log.info(f"Formatted ports: {formatted_ports}")

        # Start new container
        container = docker_client.containers.run(
            image,
            name=container_name,
            detach=True,
            restart_policy={"Name": "always"},
            ports=formatted_ports,
            network=network   # 👈 force into shared network
        )
       
       # 6. Attach it explicitly to shared network

       # Double-check network attachment (avoid duplicate connect)
        # net = docker_client.networks.get("edgecompute-net")
        # if container.name not in [c.name for c in net.containers]:
        #     net.connect(container)
        #     log.info(f"🔗 Connected {container_name} to {network_name}")

             

        # Save to DB only after successful deployment
        save_deployment(container_name, image, version, json.dumps(port_mappings), container.id)
        log.info(f"✅ Deployment successful: {container_name} running on {formatted_ports}")


        # deployment_state["status"] = "deployed"
        # deployment_state["containers"][container_name] = "running"
        # publish_status("deployed", image, container_name)

    except Exception as e:
        log.error(f"Deployment failed: {e}")
        # deployment_state["status"] = "error"
        # deployment_state["last_error"] = str(e)
        # deployment_state["containers"][container_name] = "error"

def start_container(name):
    try:
        container = docker_client.containers.get(name)
        if container.status != 'running':
            container.start()
        else:
            log.info(f"[START] Container '{name}' already running")
    except docker.errors.NotFound:
        log.error(f"[START] Container '{name}' does not exist")
        # publish_status("error", "", name, error="Container not found")
    except Exception as e:
        log.error(f"[START] Failed to start container: {e}")
        # publish_status("error", "", name, error=str(e))    

def stop_container(name):
    # container = docker_client.containers.get(name)
    # container.stop()
    # return {"status": "stopped"}
    try:
        container = docker_client.containers.get(name)
        if container.status == 'running':
            container.stop()
            # deployment_state["containers"][name] = "stopped" //2dl
            log.info(f"[STOP] Container '{name}' stopped")
            # publish_status("stopped", container.image.tags[0] if container.image.tags else "", name)//2dl
        else:
            log.info(f"[STOP] Container '{name}' is not running")
    except docker.errors.NotFound:
        log.error(f"[STOP] Container '{name}' does not exist")
        # publish_status("error", "", name, error="Container not found")//2dl
    except Exception as e:
        log.error(f"[STOP] Failed to stop container: {e}")
        # publish_status("error", "", name, error=str(e))//2dl

def restart_container(name):
    # container = docker_client.containers.get(name)
    # container.restart()
    # return {"status": "restarted"}
    try:
        container = docker_client.containers.get(name)
        container.restart()
        # deployment_state["containers"][name] = "restarted"//2dl
        log.info(f"[RESTART] Container '{name}' restarted")
        # publish_status("restarted", container.image.tags[0] if container.image.tags else "", name)//2dl
    except docker.errors.NotFound:
        log.error(f"[RESTART] Container '{name}' does not exist")
        # publish_status("error", "", name, error="Container not found")//2dl
    except Exception as e:
        log.error(f"[RESTART] Failed to restart container: {e}")
        # publish_status("error", "", name, error=str(e))   //2dl 


from datetime import datetime, timezone

def get_containers(all=True):
    """Return a list of Docker containers with uptime in hours."""
    try:
        containers = docker_client.containers.list(all=all)
        result = []
        for c in containers:
            info = c.attrs
            started_at = info["State"].get("StartedAt")

            uptime_hours = 0
            if started_at and started_at.endswith("Z"):
                try:
                    started_dt = datetime.strptime(
                        started_at[:26] + "Z", "%Y-%m-%dT%H:%M:%S.%fZ"
                    ).replace(tzinfo=timezone.utc)
                    uptime_seconds = (datetime.now(timezone.utc) - started_dt).total_seconds()
                    uptime_hours = round(uptime_seconds / 3600, 2)  # uptime in hours
                except Exception:
                    uptime_hours = 0

            result.append({
                # "id": c.id[:12],  # short ID
                "name": c.name,
                "status": c.status,
                "image": c.image.tags[0] if c.image.tags else "<none>",
                "uptime_hours": uptime_hours
            })
        return result
    except Exception as e:
        return {"error": str(e)}
