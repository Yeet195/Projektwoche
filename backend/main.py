from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from socket import *
import subprocess
import platform
import ipaddress
from parser import Parser
from database import NetworkScanDB


class NetworkScan:
    def __init__(self):
        self.config = Parser()
        self.client_ip = gethostbyname(self.config.return_var("scanner", "ip"))
        self.threads = int(self.config.return_var("scanner", "threads"))
        self.ports = self.config.return_list("scanner", "ports", "int")
        self.db = NetworkScanDB()

    def get_hostname_from_ip(self, ip: str) -> str:
        try:
            hostname, _, _ = gethostbyaddr(ip)
            return hostname
        except (herror, gaierror, timeout):
            return "Unknown"
        except Exception:
            return "Unknown"

    def get_current_ip(self) -> str | Exception:
        try:
            import socket
            import subprocess

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
                    return local_ip
            except Exception:
                pass

            try:
                result = subprocess.run(['ip', 'route', 'get', '8.8.8.8'],
                                        capture_output=True, text=True, timeout=5)
                import re
                match = re.search(r'src (\d+\.\d+\.\d+\.\d+)', result.stdout)
                if match:
                    return match.group(1)
            except Exception:
                pass

            try:
                result = subprocess.run(['hostname', '-I'],
                                        capture_output=True, text=True, timeout=5)
                ips = result.stdout.strip().split()
                for ip in ips:
                    if not ip.startswith('127.') and '.' in ip:
                        return ip
            except Exception:
                pass

            return self.config.return_var('scanner', 'fallback')

        except Exception as e:
            return e

    def get_subnet(self) -> str | Exception:
        try:
            if platform.system() == "Windows":
                result = subprocess.run(["ipconfig"], capture_output=True, text=True)
                stdout = str(result).split("stdout='", 1)[1].rsplit("'stderr=", 1)[0]

                import re
                ipv4_addresses = re.findall(r':\s+(\d{1,3}(?:\.\d{1,3}){3})', stdout)

                for address in ipv4_addresses:
                    if address.startswith("255."):
                        return address

                return "255.255.255.0"

            else:
                result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True)

                import re
                route_result = subprocess.run(['ip', 'route', 'get', '8.8.8.8'], capture_output=True, text=True)
                interface_match = re.search(r'dev (\w+)', route_result.stdout)

                if interface_match:
                    interface = interface_match.group(1)
                    result = subprocess.run(['ip', 'addr', 'show', interface], capture_output=True, text=True)
                    match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/(\d+)', result.stdout)
                    if match:
                        return match.group(2)

                return "24"

        except Exception as e:
            return "24"

    def combined_scan(self, network_range: str = None, ping_timeout: int = 2,
                      save_to_db: bool = True, notes: str = None) -> dict:
        def ping_single_host(ip_str: str) -> tuple[str, bool]:
            """Internal function to ping a single host"""
            try:
                if platform.system().lower() == 'windows':
                    cmd = ['ping', '-n', '1', '-w', str(ping_timeout), ip_str]
                else:
                    cmd = ['ping', '-c', '1', '-W', str(ping_timeout), ip_str]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=ping_timeout + 1,
                    encoding='utf-8',
                    errors='ignore'
                )
                return ip_str, result.returncode == 0

            except Exception:
                return ip_str, False

        def scan_ip_ports_and_hostname(ip: str) -> tuple[str, list[int], str]:
            scanned_ports = []
            for port in self.ports:
                try:
                    s = socket(AF_INET, SOCK_STREAM)
                    s.settimeout(1.0)
                    connection = s.connect_ex((ip, port))
                    if connection == 0:
                        scanned_ports.append(port)
                    s.close()
                except Exception:
                    continue
                time.sleep(0.01)
            hostname = self.get_hostname_from_ip(ip)
            
            return ip, scanned_ports, hostname

        results = {}

        try:
            if network_range is None:
                current_ip = self.get_current_ip()
                subnet = self.get_subnet()
                if isinstance(current_ip, Exception) or isinstance(subnet, Exception):
                    raise Exception("Could not determine current network")
                network_range = f"{current_ip}/{subnet}"

            network = ipaddress.IPv4Network(network_range, strict=False)
            host_ips = [str(ip) for ip in network.hosts()]

            print(f"Starting scan of {len(host_ips)} hosts in {network_range}...")
            start_time = time.time()

            online_hosts = []
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = [executor.submit(ping_single_host, ip) for ip in host_ips]

                for future in as_completed(futures):
                    try:
                        ip, is_online = future.result()
                        if is_online:
                            online_hosts.append(ip)
                            results[ip] = {"status": "online", "ports": [], "hostname": "Unknown"}
                        else:
                            results[ip] = {"status": "offline", "ports": [], "hostname": "Unknown"}
                    except Exception:
                        continue

            print(f"Found {len(online_hosts)} online hosts. Starting port scan and hostname resolution...")

            if online_hosts:
                with ThreadPoolExecutor(max_workers=self.threads) as executor:
                    futures = [executor.submit(scan_ip_ports_and_hostname, ip) for ip in online_hosts]

                    for future in as_completed(futures):
                        try:
                            ip, open_ports, hostname = future.result()
                            results[ip]["ports"] = open_ports
                            results[ip]["hostname"] = hostname
                        except Exception as e:
                            print(f"Error scanning IP {ip}: {e}")

            elapsed_time = time.time() - start_time
            print(f"Combined scan finished in: {elapsed_time:.2f}s")

            online_count = sum(1 for host in results.values() if host["status"] == "online")
            hosts_with_ports = sum(1 for host in results.values() if len(host["ports"]) > 0)
            print(f"Summary: {online_count}/{len(host_ips)} hosts online, {hosts_with_ports} hosts with open ports")

            if save_to_db:
                scan_id = self.db.save_scan_results(
                    results=results,
                    network_range=network_range,
                    scan_duration=elapsed_time,
                    notes=notes
                )
                print(f"Results saved to database with scan ID: {scan_id}")

            return results

        except Exception as e:
            print(f"Scan error: {e}")
            return results

    def show_scan_history(self, limit: int = 5):
        """Display recent scan history"""
        history = self.db.get_scan_history(limit)
        if not history:
            print("No scan history found.")
            return

        print(f"\nRecent Scan History (last {limit}):")
        print("-" * 80)
        for scan in history:
            print(f"ID: {scan['scan_id']} | Date: {scan['scan_date']}")
            print(f"Network: {scan['network_range']} | Hosts: {scan['online_hosts']}/{scan['total_hosts']} online")
            print(f"Duration: {scan['scan_duration']:.2f}s | Notes: {scan['notes'] or 'None'}")
            print("-" * 80)

    def show_host_history(self, ip_address: str):
        history = self.db.get_host_history(ip_address)
        if not history:
            print(f"No history found for IP {ip_address}")
            return

        print(f"\nScan History for {ip_address}:")
        print("-" * 60)
        for entry in history:
            print(f"Date: {entry['scan_date']} | Status: {entry['status']}")
            if entry['ports']:
                print(f"Open Ports: {entry['ports']}")
            if entry.get('hostname'):
                print(f"Hostname: {entry['hostname']}")
            print("-" * 60)

if __name__ == "__main__":
    networkScan = NetworkScan()