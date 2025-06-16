from flask import Flask
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import json
import threading
import time
import sys
import os

from database import NetworkScanDB
from main import NetworkScan
from parser import Parser

config = Parser()
app = Flask(__name__)
app.config['SECRET_KEY'] = config.return_var("frontend", "secret_key")

# Configure CORS for production
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:3000", "http://frontend:3000", "http://localhost:80"],
        "methods": ["GET", "POST"],
        "allow_headers": ["Content-Type"]
    }
})

# Configure SocketIO with proper CORS
socketio = SocketIO(
    app,
    cors_allowed_origins=["http://localhost:3000", "http://frontend:3000", "http://localhost:80"],
    async_mode='threading',
    logger=True,
    engineio_logger=True
)

db = NetworkScanDB()

class WebsocketNetworkScan(NetworkScan):
    def __init__(self):
        super().__init__()

    def combined_scan_web(self, network_range=None, notes=None):
        """
        Scan method for real-time updates via WebSocket
        """
        import ipaddress
        import subprocess
        import platform
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from socket import socket, AF_INET, SOCK_STREAM

        results = {}
        start_time = time.time()

        try:
            # Start scan
            socketio.emit('scan_started', {'status': 'Starting network scan'})

            if network_range is None:
                current_ip = self.get_current_ip()
                subnet = self.get_subnet()

                if isinstance(current_ip, Exception) or isinstance(subnet, Exception):
                    raise Exception("Could not determine network configuration")
                network_range = f"{current_ip}/{subnet}"

            network = ipaddress.IPv4Network(network_range, strict=False)
            host_ips = [str(ip) for ip in network.hosts()]

            total_hosts = len(host_ips)
            socketio.emit('scan_progress', {
                'phase': 'ping_sweep',
                'message': f'Starting ping sweep of {total_hosts} hosts',
                'progress': 0,
                'total': total_hosts
            })

            # Ping sweep
            online_hosts = []
            completed = 0

            def ping_host(ip_str):
                nonlocal completed
                try:
                    if platform.system().lower() == 'windows':
                        cmd = ['ping', '-n', '1', '-w', '2000', ip_str]
                    else:
                        cmd = ['ping', '-c', '1', '-W', '2', ip_str]

                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=3,
                        encoding='utf-8',
                        errors='ignore'
                    )
                    is_online = result.returncode == 0

                    completed += 1
                    progress = (completed / total_hosts) * 50  # First half of progress

                    socketio.emit('scan_progress', {
                        'phase': 'ping_sweep',
                        'message': f'Ping sweep: {completed}/{total_hosts}',
                        'progress': progress,
                        'total': total_hosts,
                        'current_ip': ip_str,
                        'status': 'online' if is_online else 'offline'
                    })

                    return ip_str, is_online
                except Exception as e:
                    completed += 1
                    print(f"Error pinging {ip_str}: {e}")
                    return ip_str, False

            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = [executor.submit(ping_host, ip) for ip in host_ips]

                for future in as_completed(futures):
                    try:
                        ip, is_online = future.result()
                        if is_online:
                            online_hosts.append(ip)
                            results[ip] = {'status': 'online', 'ports': []}
                        else:
                            results[ip] = {'status': 'offline', 'ports': []}
                    except Exception:
                        continue

            # Port scanning
            if online_hosts:
                socketio.emit('scan_progress', {
                    'phase': 'port_scan',
                    'message': f'Starting port scan of {len(online_hosts)} online hosts',
                    'progress': 50,
                    'total': len(online_hosts),
                    'online_hosts': len(online_hosts)
                })

                completed_ports = 0

                def scan_ports(ip):
                    nonlocal completed_ports
                    open_ports = []
                    for port in self.ports:
                        try:
                            s = socket(AF_INET, SOCK_STREAM)
                            s.settimeout(0.3)
                            connection = s.connect_ex((ip, port))
                            if connection == 0:
                                open_ports.append(port)
                            s.close()
                        except Exception:
                            continue
                        time.sleep(0.001)

                    completed_ports += 1
                    progress = 50 + (completed_ports / len(online_hosts)) * 50  # Second half

                    socketio.emit('scan_progress', {
                        'phase': 'port_scan',
                        'message': f'Port scan: {completed_ports}/{len(online_hosts)}',
                        'progress': progress,
                        'total': len(online_hosts),
                        'current_ip': ip,
                        'open_ports': open_ports
                    })

                    return ip, open_ports

                with ThreadPoolExecutor(max_workers=self.threads) as executor:
                    futures = [executor.submit(scan_ports, ip) for ip in online_hosts]

                    for future in as_completed(futures):
                        try:
                            ip, open_ports = future.result()
                            results[ip]['ports'] = open_ports
                        except Exception as e:
                            print(f'Error scanning IP {ip}: {e}')

            elapsed_time = time.time() - start_time

            # Save results to database
            scan_id = self.db.save_scan_results(
                results=results,
                network_range=network_range,
                scan_duration=elapsed_time,
                notes=notes
            )

            # Emit completion
            socketio.emit('scan_complete', {
                'scan_id': scan_id,
                'results': results,
                'duration': elapsed_time,
                'network_range': network_range,
                'summary': {
                    'total_hosts': len(host_ips),
                    'online_hosts': len(online_hosts),
                    'hosts_with_ports': sum(1 for host in results.values() if len(host["ports"]) > 0)
                }
            })

            return results

        except Exception as e:
            socketio.emit('scan_error', {'error': str(e)})
            return results

scanner = WebsocketNetworkScan()

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('connected', {'status': 'Connected to scan server'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('start_scan')
def handle_start_scan(data):
    network_range = data.get('network_range', None)
    notes = data.get('notes', 'WebSocket scan')

    def run_scan():
        scanner.combined_scan_web(network_range, notes)

    thread = threading.Thread(target=run_scan)
    thread.daemon = True
    thread.start()

@socketio.on('get_scan_history')
def handle_get_scan_history():
    history = db.get_scan_history()
    emit('scan_history', history)

@socketio.on('get_statistics')
def handle_get_statistics():
    stats = db.get_statistics()
    emit('statistics', stats)

if __name__ == "__main__":
    print("Starting Flask-SocketIO server...")
    socketio.run(
        app,
        debug=False,
        host='0.0.0.0',
        port=5000,
        allow_unsafe_werkzeug=True
    )