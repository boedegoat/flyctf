#!/usr/bin/env python3
"""
FlyCTF Challenge Proxy

This module provides a TCP proxy service for CTF challenges that:
1. Discovers challenges based on challenge.yaml/yml files
2. Manages Docker containers for each challenge
3. Ensures all services for a challenge are running before accepting connections
4. Proxies inbound connections to the appropriate challenge container
"""
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union, cast

import yaml

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("proxy")

# Configuration constants
CHALLENGES_DIR = Path("/app/challenges")
MAX_STARTUP_TIME = 60  # Max seconds to wait for services to start
CONN_TIMEOUT = 2.0  # Connection test timeout in seconds
POLL_INTERVAL = 0.2  # Time between service readiness checks


@dataclass
class ServiceConfig:
    """Configuration for a service within a challenge"""
    name: str
    container_id: Optional[str] = None
    ip_address: Optional[str] = None
    is_main: bool = False
    accepts_connections: bool = False
    last_error: Optional[str] = None


@dataclass
class ChallengeConfig:
    """Configuration for a challenge"""
    public_port: int
    internal_port: int
    service_name: str
    challenge_dir: Path
    compose_file: Path
    challenge_name: str
    services: Dict[str, ServiceConfig] = None
    
    def __post_init__(self):
        """Initialize services dict if not provided"""
        if self.services is None:
            self.services = {}
            # Add main service
            self.services[self.service_name] = ServiceConfig(
                name=self.service_name, 
                is_main=True
            )


class DockerHelper:
    """Helper class for Docker operations"""

    @staticmethod
    async def run_command(cmd: List[str], cwd: Optional[Path] = None) -> Tuple[str, str, int]:
        """Run a command and return stdout, stderr, and return code"""
        logger.debug(f"Running command: {' '.join(cmd)} in {cwd or '.'}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
        
        stdout_str = stdout.decode().strip() if stdout else ""
        stderr_str = stderr.decode().strip() if stderr else ""
        
        if proc.returncode != 0:
            logger.warning(
                f"Command failed (code {proc.returncode}): {' '.join(cmd)}\nStderr: {stderr_str}"
            )
            
        return stdout_str, stderr_str, proc.returncode

    @classmethod
    async def get_container_id(cls, challenge: ChallengeConfig, service_name: str) -> Optional[str]:
        """Get container ID for a service in a challenge"""
        cmd = [
            "docker-compose", 
            "-f", 
            str(challenge.compose_file),
            "ps", 
            "-q", 
            service_name
        ]
        stdout, _, returncode = await cls.run_command(cmd, cwd=challenge.challenge_dir)
        
        if returncode == 0 and stdout:
            container_ids = stdout.splitlines()
            return container_ids[0] if container_ids else None
            
        return None

    @classmethod
    async def get_container_ip(cls, container_id: str) -> Optional[str]:
        """Get IP address for a container"""
        if not container_id:
            return None
            
        cmd = ["docker", "inspect", container_id]
        stdout, _, returncode = await cls.run_command(cmd)
        
        if returncode != 0 or not stdout:
            return None
            
        try:
            data = json.loads(stdout)
            if not data:
                return None
                
            networks = data[0].get("NetworkSettings", {}).get("Networks", {})
            if not networks:
                return None
                
            # Try to find a suitable network in priority order
            ip_address = None
            
            # First try bridge or default networks
            for net_name, net_data in networks.items():
                if "bridge" in net_name.lower() or "default" in net_name.lower():
                    ip_address = net_data.get("IPAddress")
                    if ip_address:
                        break
            
            # If not found, use the first network with an IP
            if not ip_address:
                for net_data in networks.values():
                    ip_address = net_data.get("IPAddress")
                    if ip_address:
                        break
            
            return ip_address
            
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            logger.error(f"Failed to parse docker inspect output: {e}")
            return None

    @classmethod
    async def start_services(cls, challenge: ChallengeConfig) -> bool:
        """Start all services for a challenge"""
        cmd = [
            "docker-compose",
            "-f", 
            str(challenge.compose_file),
            "up", 
            "--build", 
            "-d", 
            "--remove-orphans",
        ]
        
        _, stderr, returncode = await cls.run_command(cmd, cwd=challenge.challenge_dir)
        
        if returncode != 0:
            logger.error(f"Failed to start services for {challenge.challenge_name}: {stderr}")
            return False
            
        logger.info(f"Services start command issued for challenge {challenge.challenge_name}")
        return True


class ChallengeManager:
    """Manages challenge discovery, startup, and readiness checking"""
    
    challenge_configs: Dict[int, ChallengeConfig] = {}
    
    @classmethod
    async def discover_challenges(cls) -> None:
        """Find available challenges in the challenges directory"""
        logger.info(f"Discovering challenges in {CHALLENGES_DIR}...")
        found_configs: Dict[int, ChallengeConfig] = {}
        
        if not CHALLENGES_DIR.exists():
            logger.error(f"Challenges directory {CHALLENGES_DIR} does not exist!")
            return
        
        for item in CHALLENGES_DIR.iterdir():
            if not item.is_dir() or item.name.startswith(".") or item.name == "__pycache__":
                continue
            
            # Look for docker-compose file
            compose_file = item / "docker-compose.yml"
            if not compose_file.exists():
                compose_file = item / "docker-compose.yaml"
                if not compose_file.exists():
                    logger.debug(f"Skipping {item.name}: No docker-compose file found")
                    continue
            
            # Look for challenge metadata file
            metadata_file = item / "challenge.yaml"
            if not metadata_file.exists():
                metadata_file = item / "challenge.yml"
                if not metadata_file.exists():
                    logger.debug(f"Skipping {item.name}: No challenge metadata file found")
                    continue
            
            # Parse metadata
            try:
                with open(metadata_file, 'r') as f:
                    metadata = yaml.safe_load(f)
                
                if not isinstance(metadata, dict):
                    logger.warning(f"Skipping {item.name}: Invalid metadata format")
                    continue
                
                public_port = int(metadata.get('public_port', 0))
                internal_port = int(metadata.get('internal_port', 0))
                
                if not (1024 <= public_port <= 65535):
                    logger.warning(f"Skipping {item.name}: Invalid public port {public_port}")
                    continue
                    
                if not (1 <= internal_port <= 65535):
                    logger.warning(f"Skipping {item.name}: Invalid internal port {internal_port}")
                    continue
                
                # Find service with exposed port
                service_name = None
                try:
                    with open(compose_file, 'r') as f:
                        compose_data = yaml.safe_load(f)
                    
                    services = compose_data.get('services', {})
                    
                    # First try to find a service exposing the required port
                    for svc_name, svc_data in services.items():
                        if 'expose' in svc_data and svc_data.get('expose'):
                            expose_ports = {int(p) for p in svc_data.get('expose', [])}
                            if internal_port in expose_ports:
                                service_name = svc_name
                                break
                    
                    # If not found, use any service with 'expose' directive
                    if not service_name:
                        for svc_name, svc_data in services.items():
                            if 'expose' in svc_data and svc_data.get('expose'):
                                service_name = svc_name
                                logger.warning(f"Challenge {item.name}: No service exposes port {internal_port}, using {svc_name}")
                                break
                    
                    # If still not found, use metadata or fallback to first service
                    if not service_name:
                        service_name = metadata.get('service_name')
                        if not service_name or service_name not in services:
                            if services:
                                service_name = next(iter(services.keys()))
                                logger.warning(f"Challenge {item.name}: No service specified, using first service {service_name}")
                            else:
                                logger.warning(f"Skipping {item.name}: No services defined in compose file")
                                continue

                    # Check for duplicate public ports
                    if public_port in found_configs:
                        existing = found_configs[public_port].challenge_name
                        logger.error(f"Duplicate public port {public_port} for challenges '{existing}' and '{item.name}'. Skipping '{item.name}'.")
                        continue
                    
                    # Create challenge config
                    challenge_config = ChallengeConfig(
                        public_port=public_port,
                        internal_port=internal_port,
                        service_name=service_name,
                        challenge_dir=item,
                        compose_file=compose_file,
                        challenge_name=item.name,
                    )
                    
                    # Add all services from compose file
                    for svc_name in services.keys():
                        is_main = (svc_name == service_name)
                        challenge_config.services[svc_name] = ServiceConfig(
                            name=svc_name,
                            is_main=is_main,
                        )
                    
                    found_configs[public_port] = challenge_config
                    logger.info(f"Discovered challenge '{item.name}': Public Port {public_port} -> Service '{service_name}' -> Internal Port {internal_port}")
                    
                except Exception as e:
                    logger.warning(f"Error processing compose file for {item.name}: {e}")
                    continue
                    
            except Exception as e:
                logger.warning(f"Error processing challenge {item.name}: {e}")
                continue
        
        cls.challenge_configs = found_configs
        
        if not cls.challenge_configs:
            logger.warning("No valid challenges found")
        else:
            logger.info(f"Discovered {len(cls.challenge_configs)} valid challenges")

    @classmethod
    async def check_challenge_readiness(cls, challenge: ChallengeConfig) -> bool:
        """
        Check if all services in a challenge are ready
        Returns True if all services are running with IPs and the main service accepts connections
        """
        all_ready = True
        services_ready = 0
        total_services = len(challenge.services)
        
        for service_name, service in challenge.services.items():
            # Get container ID
            container_id = await DockerHelper.get_container_id(challenge, service_name)
            if not container_id:
                service.container_id = None
                service.ip_address = None
                service.accepts_connections = False
                service.last_error = "Container not running"
                all_ready = False
                continue
            
            service.container_id = container_id
            
            # Get container IP
            ip_address = await DockerHelper.get_container_ip(container_id)
            if not ip_address:
                service.ip_address = None
                service.accepts_connections = False
                service.last_error = "No IP address assigned"
                all_ready = False
                continue
                
            service.ip_address = ip_address
            
            # For main service, check port connectivity
            if service.is_main:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(ip_address, challenge.internal_port),
                        timeout=CONN_TIMEOUT
                    )
                    writer.close()
                    await writer.wait_closed()
                    service.accepts_connections = True
                    service.last_error = None
                except (ConnectionRefusedError, asyncio.TimeoutError, OSError) as e:
                    service.accepts_connections = False
                    service.last_error = f"Connection test failed: {e}"
                    all_ready = False
                    continue
            
            services_ready += 1
        
        if all_ready:
            logger.info(f"Challenge '{challenge.challenge_name}' is fully ready with {total_services} services")
        else:
            logger.debug(f"Challenge '{challenge.challenge_name}': {services_ready}/{total_services} services ready")
            
        return all_ready

    @classmethod
    async def ensure_challenge_ready(cls, challenge: ChallengeConfig) -> bool:
        """
        Ensure the challenge is ready, starting it if necessary
        Returns True if the challenge is ready after the operation
        """
        # First check if it's already ready
        if await cls.check_challenge_readiness(challenge):
            return True
        
        # If not ready, try to start services
        logger.info(f"Starting services for challenge '{challenge.challenge_name}'...")
        if not await DockerHelper.start_services(challenge):
            logger.error(f"Failed to start services for challenge '{challenge.challenge_name}'")
            return False
        
        # Wait for services to become ready
        start_time = time.time()
        while (time.time() - start_time) < MAX_STARTUP_TIME:
            if await cls.check_challenge_readiness(challenge):
                elapsed = int(time.time() - start_time)
                logger.info(f"Challenge '{challenge.challenge_name}' ready after {elapsed}s")
                return True
            
            await asyncio.sleep(POLL_INTERVAL)
        
        # Timeout reached
        logger.error(f"Challenge '{challenge.challenge_name}' not ready after {MAX_STARTUP_TIME}s")
        return False


class ProxyService:
    """Handles TCP proxying between clients and challenge services"""
    
    @staticmethod
    async def pipe_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, 
                         description: str) -> None:
        """Pipe data from reader to writer"""
        try:
            while not reader.at_eof():
                data = await reader.read(8192)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError) as e:
            logger.debug(f"{description}: Connection closed: {e}")
        except Exception as e:
            logger.error(f"{description}: Error piping data: {e}")
        finally:
            if not writer.is_closing():
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception as e:
                    logger.debug(f"{description}: Error closing writer: {e}")

    @classmethod
    async def handle_connection(cls, client_reader: asyncio.StreamReader, 
                              client_writer: asyncio.StreamWriter) -> None:
        """Handle incoming client connection"""
        peername = client_writer.get_extra_info('peername')
        sockname = client_writer.get_extra_info('sockname')
        listen_port = sockname[1]
        
        logger.info(f"Received connection from {peername} on port {listen_port}")
        
        # Check if we have a challenge for this port
        if listen_port not in ChallengeManager.challenge_configs:
            logger.error(f"No challenge configured for port {listen_port}")
            client_writer.close()
            await client_writer.wait_closed()
            return
        
        challenge = ChallengeManager.challenge_configs[listen_port]
        
        # Ensure the challenge is ready
        if not await ChallengeManager.ensure_challenge_ready(challenge):
            logger.error(f"Failed to prepare challenge '{challenge.challenge_name}' for connection")
            client_writer.close()
            await client_writer.wait_closed()
            return
        
        # Get main service details
        main_service = challenge.services[challenge.service_name]
        if not main_service.ip_address or not main_service.accepts_connections:
            logger.error(f"Main service for '{challenge.challenge_name}' is not accepting connections")
            client_writer.close()
            await client_writer.wait_closed()
            return
        
        # Connect to target
        target_ip = main_service.ip_address
        target_port = challenge.internal_port
        
        try:
            logger.info(f"Proxying {peername} -> {target_ip}:{target_port} for challenge '{challenge.challenge_name}'")
            target_reader, target_writer = await asyncio.open_connection(target_ip, target_port)
            
            # Set up bidirectional proxy
            client_to_target = asyncio.create_task(
                cls.pipe_stream(client_reader, target_writer, f"{peername} -> {target_ip}:{target_port}")
            )
            target_to_client = asyncio.create_task(
                cls.pipe_stream(target_reader, client_writer, f"{target_ip}:{target_port} -> {peername}")
            )
            
            # Wait for either direction to complete
            done, pending = await asyncio.wait(
                [client_to_target, target_to_client],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                    
        except ConnectionRefusedError:
            logger.error(f"Connection refused to {target_ip}:{target_port}")
        except Exception as e:
            logger.error(f"Error proxying to {target_ip}:{target_port}: {e}")
        finally:
            logger.info(f"Connection from {peername} closed")
            # Ensure all connections are properly closed
            for writer in [w for w in [client_writer, locals().get('target_writer')] 
                          if w and not w.is_closing()]:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass


async def main() -> None:
    """Main entry point for the proxy service"""
    logger.info("Starting FlyCTF proxy service")
    
    # Discover challenges
    await ChallengeManager.discover_challenges()
    
    if not ChallengeManager.challenge_configs:
        logger.warning("No challenges found. Proxy will run but serve no challenges.")
    
    # Start servers for each challenge
    servers = []
    for port, challenge in ChallengeManager.challenge_configs.items():
        try:
            server = await asyncio.start_server(
                ProxyService.handle_connection,
                '0.0.0.0',
                port
            )
            servers.append(server)
            logger.info(f"Listening on 0.0.0.0:{port} for challenge '{challenge.challenge_name}'")
        except OSError as e:
            logger.error(f"Failed to bind to port {port}: {e}")
    
    if servers:
        # Wait for all servers to complete (they run forever)
        await asyncio.gather(*(server.serve_forever() for server in servers))
    else:
        # Keep the application running even if no servers started
        logger.warning("No servers started. Waiting indefinitely.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Proxy shutting down")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)