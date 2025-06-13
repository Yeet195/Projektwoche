from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
from socket import *
import subprocess
import platform
import re
import ipaddress
from parser import Parser


class NetworkScan:
    def __init__(self):
        self.config = Parser()
        self.client_ip = gethostbyname(self.config.return_var("scanner", "ip"))
        self.threads = int(self.config.return_var("scanner", "threads"))

        # Ports to scan for
        self.ports = self.config.return_list("scanner", "ports", "int")

    def get_current_ip(self) -> str | Exception:
        """
        Get the ip of current client

        :return:
            str: ip address
        """
        try:
            with socket(AF_INET, SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]

            return local_ip
        except Exception as e:
            return e

    def get_subnet(self) -> str | Exception:
        """
        Get Subnet mask

        :return:
            str: subnet mask
        """
        try:
            if platform.system() == "Windows":
                # Execute ipconfig in terminal
                result = subprocess.run(["ipconfig"], capture_output=True, text=True)

                # Get stdout string
                stdout = str(result).split("stdout='", 1)[1].rsplit("'stderr=", 1)[0]

                # Find ips after colon
                ipv4_addresses = re.findall(r':\s+(\d{1,3}(?:\.\d{1,3}){3})', stdout)

                # Remove everything that does not start with "255."
                for address in ipv4_addresses:
                    if not address.startswith("255."):
                        ipv4_addresses.remove(address)
                subnet_mask: str = ipv4_addresses[0]

                return subnet_mask
        except Exception as e:
            return e

    def get_ips(self, ip: str, subnet: str) -> list[str] | None:
        """
        Get all ips of the clients network

        :return:
            list[str]: list of all possible ips in network
        """
        # create the network object
        net_obj = ipaddress.IPv4Network(f"{ip}/{subnet}", strict=False)

        # Get usable ips excluding network and broadcast
        all_ips = [str(ip) for ip in net_obj.hosts()]

        return all_ips

    def ping_sweep(self, network_range: str = None, timeout: int = 2, verbose: bool = True) -> dict:
        """
        Perform ping sweep to discover online hosts in the network

        :param network_range: CIDR notation network (e.g., "192.168.1.0/24"). If None, uses current network
        :param timeout: Ping timeout in seconds
        :param verbose: Print progress during scan
        :return: dict with online/offline hosts and summary stats
        """

        def ping_single_host(ip_str: str) -> tuple[str, bool]:
            """Internal function to ping a single host"""
            try:
                # Determine ping parameters based on OS
                if platform.system().lower() == 'windows':
                    cmd = ['ping', '-n', '1', '-w', str(timeout * 1000), ip_str]
                else:
                    cmd = ['ping', '-c', '1', '-W', str(timeout * 1000), ip_str]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout + 1,
                    encoding='utf-8',
                    errors='ignore'
                )
                return ip_str, result.returncode == 0

            except subprocess.TimeoutExpired:
                return ip_str, False
            except UnicodeDecodeError:
                # Fallback: try without text capture
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        timeout=timeout + 1
                    )
                    return ip_str, result.returncode == 0
                except Exception:
                    return ip_str, False
            except Exception:
                return ip_str, False

        # Initialize results
        results = {
            "online": [],
            "offline": [],
            "summary": {}
        }

        try:
            # Determine network range
            if network_range is None:
                # Use current network
                current_ip = self.get_current_ip()
                subnet = self.get_subnet()
                if isinstance(current_ip, Exception) or isinstance(subnet, Exception):
                    raise Exception("Could not determine current network")
                network_range = f"{current_ip}/{subnet}"

            # Parse network range
            network = ipaddress.IPv4Network(network_range, strict=False)
            host_ips = [str(ip) for ip in network.hosts()]

            start_time = time.time()

            # Perform ping sweep
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = [executor.submit(ping_single_host, ip) for ip in host_ips]

                completed = 0
                for future in as_completed(futures):
                    try:
                        ip, is_online = future.result()
                        completed += 1

                        if is_online:
                            results["online"].append(ip)
                            if verbose:
                                print(f"{ip:<15} - ONLINE")
                        else:
                            results["offline"].append(ip)
                            if verbose:
                                print(f"{ip:<15} - OFFLINE")

                    except Exception:
                        results["offline"].append("unknown")


            end_time = time.time()
            scan_duration = end_time - start_time

            results["summary"] = {
                "total_scanned": len(host_ips),
                "online_count": len(results["online"]),
                "offline_count": len(results["offline"]),
                "scan_duration": round(scan_duration, 2),
                "hosts_per_second": round(len(host_ips) / scan_duration, 2),
                "success_rate": round((len(results["online"]) / len(host_ips)) * 100, 2) if host_ips else 0
            }

            return results

        except Exception as e:
            print(f"Ping sweep error: {e}")
            return results

    def scan_ports(self) -> dict[str, list[int]]:
        """
        Scan for defined ports on target ip.

        :return:
            list: list of open ports
        """
        open_ports: dict[str, list[int]] = {}
        lock = threading.Lock()
        scanned_count = 0
        total_ips = 0

        def scan_ip_ports(ip: str) -> tuple[str, list[int]]:
            """
            scan all ports for ip address

            :param ip:

            :return:
                tuple[str, list[int]]: returns ip with all open ports
            """
            nonlocal scanned_count
            scanned_ports = []

            for port in self.ports:
                try:
                    s = socket(AF_INET, SOCK_STREAM)
                    s.settimeout(0.3)
                    connection = s.connect_ex((ip, port))
                    if connection == 0:
                        scanned_ports.append(port)
                    s.close()
                except Exception:
                    continue

                # small delay for lower powered systems
                time.sleep(0.001)

            return ip, scanned_ports

        ips = list(self.get_ips(self.get_current_ip(), self.get_subnet()))
        max_workers = self.threads
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(scan_ip_ports, ip) for ip in ips]

            for future in as_completed(futures):
                try:
                    ip, scanned_ports = future.result()
                    if scanned_ports:
                        open_ports[ip] = scanned_ports
                except Exception as e:
                    print(f"Error scanning IP: {e}")

        elapsed_time = time.time() - start_time
        print(f"Port scan finished in: {elapsed_time}s")

        return open_ports

    def combined_scan(self, network_range: str = None, ping_timeout: int = 2, verbose: bool = True) -> dict:
        """
        Perform ping sweep first, then port scan only on online hosts

        :param network_range: CIDR notation network (e.g., "192.168.1.0/24"). If None, uses current network
        :param ping_timeout: Ping timeout in seconds
        :param verbose: Print progress during scan
        :return: dict with ping results and port scan results
        """

        # Perform ping sweep
        ping_results = self.ping_sweep(network_range, ping_timeout, verbose)

        if not ping_results["online"]:
            return {"ping_results": ping_results, "port_results": {}}

        print(f"\n🔌 Starting port scan on {len(ping_results['online'])} online hosts...")

        # Port scan only online hosts
        def scan_ip_ports(ip: str) -> tuple[str, list[int]]:
            scanned_ports = []
            for port in self.ports:
                try:
                    s = socket(AF_INET, SOCK_STREAM)
                    s.settimeout(0.3)
                    connection = s.connect_ex((ip, port))
                    if connection == 0:
                        scanned_ports.append(port)
                    s.close()
                except Exception:
                    continue
                time.sleep(0.001)
            return ip, scanned_ports

        port_results = {}
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = [executor.submit(scan_ip_ports, ip) for ip in ping_results["online"]]

            for future in as_completed(futures):
                try:
                    ip, scanned_ports = future.result()
                    if scanned_ports:
                        port_results[ip] = scanned_ports
                        if verbose:
                            print(f"🔌 {ip}: Open ports {scanned_ports}")
                except Exception as e:
                    print(f"Error scanning IP: {e}")

        elapsed_time = time.time() - start_time
        print(f"Port scan finished in: {elapsed_time}s")

        return {"ping_results": ping_results, "port_results": port_results}

networkScan = NetworkScan()

#Just ping sweep
#ping_results = networkScan.ping_sweep()

# Just port scan
# port_results = networkScan.scan_ports()

# Combined scan
combined_results = networkScan.combined_scan()