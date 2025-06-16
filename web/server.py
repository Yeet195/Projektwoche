from operator import is_not

from flask import Flask
from flask_socketio import SocketIO, emit
from flask_cors import CORS, cross_origin
import json
import threading
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import NetworkScanDB
from main import NetworkScan
from parser import Parser

config = Parser()
app = Flask(__name__)
app.config['SECRET_KEY'] = config.return_var("frontend", "secret_key")
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

db = NetworkScanDB()

class WebsocketNetworkScan(NetworkScan):
    def __init__(self):
        super().__init__()

    def combined_scan_web(self, network_range=None, notes=None):
        """
        Scan method for real-time updates

        :param network_range:
        :param notes:
        :return:
        """
        import ipaddress
        import subprocess
        import platform
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}
        start_time = time.time()

        try:
            # start scan
            socketio.emit('scan_started', {'status' : 'starting scan'})

            if network_range is None:
                current_ip = self.get_current_ip()
                subnet = self.get_subnet()

                if isinstance(current_ip, Exception) or isinstance(subnet, Exception):
                    raise Exception("Could not determine network specifics")
                network_range = f"{current_ip}/{subnet}"

            network = ipaddress.IPv4Network(network_range, strict=False)
            host_ips = [str(ip) for ip in network.hosts()]

            total_hosts = len(host_ips)
            socketio.emit('scan_progress', {
                'phase' : 'ping_sweep',
                'message' : f'starting ping sweep of {total_hosts} hosts',
                'progress' : 0,
                'total' : total_hosts
            })

            # Ping sweep
            online_hosts = []
            completed = 0

            def ping_prog(ip_str):
                nonlocal completed
                try:
                    if platform.system().lower() == 'windows':
                        cmd = ['ping', '-n', '1', '-w', '2000', ip_str]
                    else:
                        cmd = ['ping', '-n', '1', '-w', '2000', ip_str]

                    results = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                    is_online = results.returncode == 0

                    completed += 1
                    progress = (completed / total_hosts) * 100

                    socketio.emit('scan_progress', {
                        'phase' : 'ping_sweep',
                        'message' : f'Ping sweep: {completed}/{total_hosts}',
                        'progress' : progress,
                        'total' : total_hosts,
                        'current_ip' : ip_str,
                        'status' : 'online' if is_online else 'offline'
                    })

                    return ip_str, is_online
                except Exception:
                    completed += 1
                    return ip_str, False

            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = [executor.submit(ping_prog, ip) for ip in host_ips]

                for future in as_completed(futures):
                    try:
                        ip, is_online = future.result()
                        if is_online:
                            online_hosts.append(ip)
                            results[ip] = {'status' : 'online', 'ports' : []}
                        else:
                            results[ip] = {'status': 'offline', 'ports': []}
                    except Exception:
                        continue

            if online_hosts:
                socketio.emit('scan_progress', {
                    'phase' : 'port_scan',
                    'message' : f'starting port scan of {len(online_hosts)} online',
                    'progress' : 0,
                    'total' : len(online_hosts),
                    'online_hosts': len(online_hosts)
                })

                completed_ports = 0

                def ports_prog(ip):
                    nonlocal completed_ports
                    scanned_ports = []
                    for port in self.ports:
                        try:
                            from socket import socket, AF_INET, SOCK_STREAM
                            s = socket(AF_INET, SOCK_STREAM)
                            s.settimeout(0.3)
                            connection = s.connect_ex((ip, port))
                            if connection == 0:
                                scanned_ports.append(port)
                            s.close()
                        except Exception:
                            continue
                        time.sleep(0.001)

                    completed_ports += 1
                    progress = (completed_ports / len(online_hosts)) * 100

                    socketio.emit('scan_progress', {
                        'phase': 'port_scan',
                        'message': f'Port scan: {completed_ports}/{len(online_hosts)}',
                        'progress': progress,
                        'total': len(online_hosts),
                        'current_ip': ip,
                        'open_ports': scanned_ports
                    })

                    return ip, scanned_ports

                with ThreadPoolExecutor(max_workers=self.threads) as executor:
                    futures = [executor.submit(ports_prog, ip) for ip in online_hosts]

                    for future in as_completed(futures):
                        try:
                            ip, open_ports = future.result()
                            results[ip]['ports'] = open_ports
                        except Exception as e:
                            print(f'Error scanning IP: {ip}: {e}')

            elapsed_time = time.time() - start_time

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
            socketio.emit('scan_error', {
                'error' : str(e)})
            return results

scanner = WebsocketNetworkScan()

@socketio.on('connect')
def handle_connect():
    print('client connected')
    emit('connected', {'status' : 'connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    print('client disconnected')

@socketio.on('start_scan')
def handle_start_scan(data):
    network_range = data.get('network_range', None)
    notes = data.get('notes', 'WebSocket scan')

    def run_scan():
        scanner.combined_scan_web(network_range, notes)

    thread = threading.Thread(target=run_scan())
    thread.daemon = True
    thread.start()

@socketio.on('get_scan_history')
def handle_get_status():
    stats = db.get_statistics()
    emit('statistics', stats)

if __name__ == "__main__":
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)

