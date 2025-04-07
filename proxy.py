#!/usr/bin/env python3
import asyncio
import logging
import sys
import json
from pathlib import Path
import yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
CHALLENGES_DIR = Path("/app/challenges")
CHALLENGE_CONFIG = {} # Stores {public_port: config_dict}

# --- Utility Functions --- (Keep run_subprocess as before)
async def run_subprocess(cmd, cwd=None):
    """Helper to run subprocesses and return stdout, stderr, code."""
    logging.debug(f"Running command: {' '.join(cmd)} in {cwd or '.'}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd
    )
    stdout, stderr = await proc.communicate()
    stdout_str = stdout.decode().strip()
    stderr_str = stderr.decode().strip()
    if proc.returncode != 0:
        logging.warning(f"Command failed (code {proc.returncode}): {' '.join(cmd)}\nStderr: {stderr_str}")
    return stdout_str, stderr_str, proc.returncode

# --- Challenge Discovery (MODIFIED) ---
def find_challenges():
    """Scans the challenges directory using metadata files (challenge.yaml or challenge.yml)."""
    logging.info(f"Scanning for challenges in {CHALLENGES_DIR} using challenge.yaml or challenge.yml...")
    found_configs = {} # Temp dict to check for duplicate public ports

    for item in CHALLENGES_DIR.iterdir():
        if item.is_dir():
            # Ignore common non-challenge dirs
            if item.name.startswith('.') or item.name == '__pycache__':
                continue

            compose_file = item / "docker-compose.yml"
            metadata_file = None # Path object of the found metadata file
            metadata_filename_used = None # String 'challenge.yaml' or 'challenge.yml'

            # --- Check for challenge.yaml or challenge.yml ---
            metadata_yaml_path = item / "challenge.yaml"
            metadata_yml_path = item / "challenge.yml"

            if metadata_yaml_path.exists():
                metadata_file = metadata_yaml_path
                metadata_filename_used = "challenge.yaml"
            elif metadata_yml_path.exists():
                metadata_file = metadata_yml_path
                metadata_filename_used = "challenge.yml"
            # --- ---

            # Proceed only if a metadata file AND a compose file were found
            if metadata_file and compose_file.exists():
                challenge_folder_name = item.name
                logging.debug(f"Found potential challenge '{challenge_folder_name}' with '{metadata_filename_used}' and '{compose_file.name}'")
                try:
                    # --- Load Metadata (using the found metadata_file path) ---
                    with open(metadata_file, 'r') as f:
                        metadata = yaml.safe_load(f)

                    if not isinstance(metadata, dict):
                         raise ValueError(f"{metadata_filename_used} is not a valid dictionary.")

                    public_port = int(metadata['public_port'])
                    internal_port = int(metadata['internal_port'])
                    # Use service_name from metadata if provided, else default to folder name
                    service_name = metadata.get('service_name', challenge_folder_name)

                    # --- Validation ---
                    if not (1024 <= public_port <= 65535):
                        raise ValueError("Public port out of range")
                    if not (1 <= internal_port <= 65535):
                         raise ValueError("Internal port out of range")

                    # --- Optional: Verify expose port in docker-compose.yml matches internal_port ---
                    try:
                         with open(compose_file, 'r') as f_compose:
                              compose_data = yaml.safe_load(f_compose)
                         # Check if service exists in compose file
                         if service_name not in compose_data.get('services', {}):
                              raise ValueError(f"Service name '{service_name}' not found in {compose_file.name}")

                         service_data = compose_data['services'][service_name]
                         expose_ports = service_data.get('expose', [])
                         exposed_internal_ports = {int(p) for p in expose_ports}

                         if internal_port not in exposed_internal_ports:
                              logging.warning(f"Challenge '{challenge_folder_name}': Internal port {internal_port} from {metadata_filename_used} "
                                              f"is NOT listed in 'expose:' section ({exposed_internal_ports}) for service '{service_name}' in {compose_file.name}. "
                                              f"Connections might fail.")
                    except FileNotFoundError:
                         raise ValueError(f"{compose_file.name} not found during verification.") # Should not happen here
                    except Exception as compose_err:
                         logging.warning(f"Challenge '{challenge_folder_name}': Could not verify expose port in {compose_file.name}. Error: {compose_err}")
                         # Decide if you want to continue despite warning or skip


                    # --- Check for duplicate public port assignment before adding ---
                    if public_port in found_configs:
                         logging.error(f"Duplicate public port {public_port} defined by both '{found_configs[public_port]['challenge_folder_name']}' (using {found_configs[public_port]['metadata_filename_used']}) and '{challenge_folder_name}' (using {metadata_filename_used}). Skipping '{challenge_folder_name}'.")
                         continue # Skip this challenge

                    # --- Store valid configuration ---
                    config_data = {
                        "dir": item,
                        "compose_file": compose_file,
                        "service_name": service_name,
                        "internal_port": internal_port,
                        "challenge_folder_name": challenge_folder_name, # Store original folder name
                        "metadata_filename_used": metadata_filename_used # Store which filename was found
                    }
                    found_configs[public_port] = config_data # Add to temp dict first
                    logging.info(f"Discovered challenge '{challenge_folder_name}' using '{metadata_filename_used}': Public Port {public_port} -> Service '{service_name}' -> Internal Port {internal_port}")

                # --- Catch errors during parsing/validation for this specific challenge ---
                except (ValueError, yaml.YAMLError, KeyError, TypeError) as e:
                     logging.warning(f"Skipping challenge in folder '{challenge_folder_name}': Could not parse valid config from {metadata_filename_used} or related files. Error: {e}")
                except FileNotFoundError as e:
                     logging.warning(f"Skipping challenge in folder '{challenge_folder_name}': File not found during processing. Error: {e}")

            # --- Log warnings for potential misconfigurations ---
            elif item.name != '__pycache__': # Avoid logging for python cache dirs
                if not metadata_file and compose_file.exists():
                     logging.warning(f"Skipping directory '{item.name}': Found {compose_file.name} but no challenge.yaml or challenge.yml.")
                elif metadata_file and not compose_file.exists():
                     logging.warning(f"Skipping directory '{item.name}': Found {metadata_filename_used} but no {compose_file.name}.")
                # If neither exists, no warning needed, just not a challenge dir


    # Assign successfully parsed configs to the global dict
    global CHALLENGE_CONFIG
    CHALLENGE_CONFIG = found_configs

    if not CHALLENGE_CONFIG:
         logging.warning("No valid challenges found after scanning. Proxy will run but serve no challenges.")
         # No longer exiting here, allows adding challenges later maybe? Or user can decide if exit is needed.


# --- Docker Interaction --- (Keep get_container_id, get_container_ip, is_service_running, start_service as before)
async def get_container_id(config):
    """Get the container ID for the running service."""
    cmd = [
        "docker-compose", "-f", str(config["compose_file"]),
        "ps", "-q", config["service_name"]
    ]
    stdout, _, returncode = await run_subprocess(cmd, cwd=config["dir"])
    if returncode == 0 and stdout:
        ids = stdout.splitlines()
        return ids[0] if ids else None # Return first ID if exists
    return None

async def get_container_ip(container_id):
    """Inspect the container to get its primary IP address."""
    if not container_id:
        return None
    cmd = ["docker", "inspect", container_id]
    stdout, _, returncode = await run_subprocess(cmd)
    if returncode == 0 and stdout:
        try:
            data = json.loads(stdout)
            if data:
                networks = data[0].get("NetworkSettings", {}).get("Networks", {})
                if networks:
                    ip_address = None
                    # Prioritize common network names, then fallback
                    for net_name, net_settings in networks.items():
                         if "bridge" in net_name or "default" in net_name:
                              ip_address = net_settings.get("IPAddress")
                              if ip_address: break
                    if not ip_address: # Fallback to first available IP
                         first_network = next(iter(networks.values()), None)
                         if first_network: ip_address = first_network.get("IPAddress")

                    if ip_address:
                        logging.debug(f"Found IP {ip_address} for container {container_id}")
                        return ip_address
        except (json.JSONDecodeError, IndexError, KeyError, StopIteration, TypeError) as e:
            logging.error(f"Failed to parse docker inspect output for {container_id}: {e}")
    logging.warning(f"Could not determine IP address for container {container_id}")
    return None


async def is_service_running(config):
    """Check if the service's container is running and get its IP."""
    container_id = await get_container_id(config)
    if container_id:
         ip = await get_container_ip(container_id)
         return ip is not None
    return False

async def start_service(config):
    """Start the docker-compose service."""
    service_name = config['service_name']
    public_port = next((p for p, c in CHALLENGE_CONFIG.items() if c['service_name'] == service_name), 'N/A') # Find public port for logging
    logging.info(f"Starting service '{service_name}' for public port {public_port}...")
    cmd = [
        "docker-compose", "-f", str(config["compose_file"]),
        "up", "--build", "-d", "--remove-orphans", service_name
    ]
    _, stderr, returncode = await run_subprocess(cmd, cwd=config["dir"])
    if returncode != 0:
        logging.error(f"Failed to start service '{service_name}'. Error: {stderr}")
        return False

    logging.info(f"Service '{service_name}' start command issued. Waiting briefly...")
    await asyncio.sleep(3)

    container_id = await get_container_id(config)
    ip_address = await get_container_ip(container_id)
    if ip_address:
         logging.info(f"Service '{service_name}' confirmed running with IP {ip_address}.")
         return True
    else:
         logging.error(f"Service '{service_name}' failed to become ready after start command.")
         return False


# --- Proxy Logic --- (Keep pipe_stream and handle_connection as before)
async def pipe_stream(reader, writer, peer_name):
    """Reads from reader and writes to writer until EOF."""
    # (Implementation unchanged)
    try:
        while not reader.at_eof():
            data = await reader.read(4096)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError) as e:
        logging.debug(f"Connection closed/reset for {peer_name}: {e}")
    except Exception as e:
        logging.error(f"Error piping stream for {peer_name}: {e}")
    finally:
        if writer and not writer.is_closing():
             try:
                writer.close()
                await writer.wait_closed()
             except Exception as close_e:
                 logging.debug(f"Error closing writer for {peer_name}: {close_e}")


async def handle_connection(client_reader, client_writer):
    """Handles a new client connection."""
    # (Implementation unchanged)
    peername = client_writer.get_extra_info('peername')
    sockname = client_writer.get_extra_info('sockname')
    listen_port = sockname[1] # This is the public port (e.g., 5000)
    logging.info(f"Received connection from {peername} on public port {listen_port}")

    if listen_port not in CHALLENGE_CONFIG:
        logging.error(f"No challenge configured for port {listen_port}. Closing connection.")
        client_writer.close()
        await client_writer.wait_closed()
        return

    config = CHALLENGE_CONFIG[listen_port]
    service_name = config['service_name']

    container_id = await get_container_id(config)
    target_ip = await get_container_ip(container_id)

    if not target_ip:
        logging.info(f"Service '{service_name}' not running or has no IP. Attempting to start...")
        if not await start_service(config):
            logging.error(f"Could not start service '{service_name}' for port {listen_port}. Closing connection.")
            client_writer.close()
            await client_writer.wait_closed()
            return
        else:
             container_id = await get_container_id(config)
             target_ip = await get_container_ip(container_id)
             if not target_ip:
                 logging.error(f"Service '{service_name}' started but failed to get IP for port {listen_port}. Closing connection.")
                 client_writer.close()
                 await client_writer.wait_closed()
                 return
             logging.info(f"Service '{service_name}' for port {listen_port} is now running.")
    else:
         logging.info(f"Service '{service_name}' for port {listen_port} already running with IP {target_ip}.")

    target_port = config["internal_port"]
    target_reader, target_writer = None, None
    try:
        logging.info(f"Proxying {peername} -> {target_ip}:{target_port} for challenge '{config['challenge_folder_name']}' (service: {service_name})")
        target_reader, target_writer = await asyncio.open_connection(target_ip, target_port)

        client_to_target = asyncio.create_task(pipe_stream(client_reader, target_writer, f"{peername} -> target"))
        target_to_client = asyncio.create_task(pipe_stream(target_reader, client_writer, f"target -> {peername}"))
        await asyncio.wait([client_to_target, target_to_client], return_when=asyncio.FIRST_COMPLETED)

    except ConnectionRefusedError:
         logging.error(f"Connection refused connecting to {target_ip}:{target_port}. Is service '{service_name}' running & listening internally?")
    except OSError as e:
         logging.error(f"OS error connecting or proxying to {target_ip}:{target_port}: {e}")
    except Exception as e:
        logging.error(f"Proxy error for port {listen_port} -> {target_ip}:{target_port}: {e}")
    finally:
        logging.info(f"Closing connection from {peername} on port {listen_port}")
        writers_to_close = [w for w in (target_writer, client_writer) if w and not w.is_closing()]
        for writer in writers_to_close:
            try: writer.close(); await writer.wait_closed()
            except Exception: pass
        tasks_to_cancel = [t for t in [locals().get('client_to_target', None), locals().get('target_to_client', None)] if t and not t.done()]
        for task in tasks_to_cancel:
              if task:
                  task.cancel()
                  try: await task
                  except asyncio.CancelledError: pass


# --- Main Server --- (Keep main function as before)
async def main():
    """Starts the server listening on all configured challenge ports."""
    try:
        import yaml
    except ImportError:
        logging.error("PyYAML is not available. Ensure 'py3-yaml' is in apk add command in Dockerfile.")
        sys.exit(1)

    find_challenges() # Discover challenges using the new method

    servers = []
    for port in CHALLENGE_CONFIG.keys():
        try:
            server = await asyncio.start_server(
                handle_connection, '0.0.0.0', port)
            servers.append(server)
            logging.info(f"Proxy listening on 0.0.0.0:{port}")
        except OSError as e:
             logging.error(f"Failed to bind to public port {port}: {e}.")
        except Exception as e:
             logging.error(f"Failed to start server on port {port}: {e}")

    if not servers:
         if CHALLENGE_CONFIG:
              logging.error("No proxy servers could be started, although challenges were configured. Exiting.")
              sys.exit(1)
         else:
              logging.warning("No challenges configured or found. Proxy running but serving nothing.")

    if servers:
        await asyncio.gather(*(s.serve_forever() for s in servers))
    else:
        await asyncio.Event().wait() # Keep container running even if no challenges loaded


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Proxy shutting down.")