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

    def get_current_ip(self) -> str | Exception:
        """Get the ip of current client"""
        try:
            with socket(AF_INET, SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
            return local_ip
        except Exception as e:
            return e

    def get_subnet(self) -> str | Exception:
        """Get Subnet mask"""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(["ipconfig"], capture_output=True, text=True)
                stdout = str(result).split("stdout='", 1)[1].rsplit("'stderr=", 1)[0]

                import re
                ipv4_addresses = re.findall(r':\s+(\d{1,3}(?:\.\d{1,3}){3})', stdout)

                for address in ipv4_addresses:
                    if address.startswith("255."):
                        return address

                # Fallback to common subnet mask
                return "255.255.255.0"
        except Exception as e:
            return e

    def combined_scan(self, network_range: str = None, ping_timeout: int = 2,
                      save_to_db: bool = True, notes: str = None) -> dict:
        """
        Perform ping sweep first, then port scan only on online hosts
        Returns results and optionally saves to database
        """

        def ping_single_host(ip_str: str) -> tuple[str, bool]:
            """Internal function to ping a single host"""
            try:
                if platform.system().lower() == 'windows':
                    cmd = ['ping', '-n', '1', '-w', str(ping_timeout * 1000), ip_str]
                else:
                    cmd = ['ping', '-c', '1', '-W', str(ping_timeout * 1000), ip_str]

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

        def scan_ip_ports(ip: str) -> tuple[str, list[int]]:
            """Scan all ports for an IP address"""
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

        # Initialize results dictionary
        results = {}

        try:
            # Determine network range
            if network_range is None:
                current_ip = self.get_current_ip()
                subnet = self.get_subnet()
                if isinstance(current_ip, Exception) or isinstance(subnet, Exception):
                    raise Exception("Could not determine current network")
                network_range = f"{current_ip}/{subnet}"

            # Parse network range
            network = ipaddress.IPv4Network(network_range, strict=False)
            host_ips = [str(ip) for ip in network.hosts()]

            print(f"Starting scan of {len(host_ips)} hosts in {network_range}...")
            start_time = time.time()

            # Step 1: Ping sweep to find online hosts
            online_hosts = []
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = [executor.submit(ping_single_host, ip) for ip in host_ips]

                for future in as_completed(futures):
                    try:
                        ip, is_online = future.result()
                        if is_online:
                            online_hosts.append(ip)
                            results[ip] = {"status": "online", "ports": []}
                        else:
                            results[ip] = {"status": "offline", "ports": []}
                    except Exception:
                        continue

            print(f"Found {len(online_hosts)} online hosts. Starting port scan...")

            # Step 2: Port scan only online hosts
            if online_hosts:
                with ThreadPoolExecutor(max_workers=self.threads) as executor:
                    futures = [executor.submit(scan_ip_ports, ip) for ip in online_hosts]

                    for future in as_completed(futures):
                        try:
                            ip, open_ports = future.result()
                            results[ip]["ports"] = open_ports
                        except Exception as e:
                            print(f"Error scanning IP {ip}: {e}")

            elapsed_time = time.time() - start_time
            print(f"Combined scan finished in: {elapsed_time:.2f}s")

            # Print summary
            online_count = sum(1 for host in results.values() if host["status"] == "online")
            hosts_with_ports = sum(1 for host in results.values() if len(host["ports"]) > 0)
            print(f"Summary: {online_count}/{len(host_ips)} hosts online, {hosts_with_ports} hosts with open ports")

            # Save to database if requested
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
        """Display scan history for a specific IP"""
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
            print("-" * 60)

if __name__ == "__main__":
    networkScan = NetworkScan()

    # Perform scan and save to database
    scan_results = networkScan.combined_scan(notes="Weekly network scan")

    # Show scan history
    networkScan.show_scan_history()

    # Show database statistics
    stats = networkScan.db.get_statistics()
    print(f"\nDatabase Statistics:")
    print(f"Total scans: {stats['total_scans']}")
    print(f"Unique IPs scanned: {stats['unique_ips_scanned']}")
    print(f"Last scan: {stats['last_scan_date']}")
    print(f"Average online hosts per scan: {stats['average_online_hosts']}")

    # Example: Show history for a specific IP
    # networkScan.show_host_history("192.168.1.1")