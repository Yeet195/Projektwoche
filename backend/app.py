from flask import Flask, redirect
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import json
import threading
import time
import sys
import os
from datetime import datetime, timedelta

from database import NetworkScanDB
from main import NetworkScan
from parser import Parser

config = Parser()
app = Flask(__name__)
app.config['SECRET_KEY'] = config.return_var("frontend", "secret_key")
FRONTEND_URL = config.return_var("frontend", "url")

CORS(app, resources={
	r"/*": {
		"origins": ["*"],
		"methods": ["GET", "POST", "OPTIONS"],
		"allow_headers": ["Content-Type", "Authorization"],
		"supports_credentials": False
	}
})

socketio = SocketIO(
	app,
	cors_allowed_origins="*",
	async_mode='threading',
	logger=True,
	engineio_logger=True,
	allow_upgrades=True,
	ping_timeout=60,
	ping_interval=25
)

db = NetworkScanDB()

auto_scan_thread = None
auto_scan_running = False
next_auto_scan_time = None

class WebsocketNetworkScan(NetworkScan):
	def __init__(self):
		super().__init__()

	def combined_scan_web(self, app, network_range=None, notes=None, is_auto_scan=False):
		"""
		Scan method for real-time updates via WebSocket
		Now includes hostname resolution
		"""
		from flask import current_app
		import ipaddress
		import subprocess
		import platform
		from concurrent.futures import ThreadPoolExecutor, as_completed
		from socket import socket, AF_INET, SOCK_STREAM, gethostbyaddr, herror, gaierror, timeout

		def get_hostname_from_ip(ip: str) -> str:
			"""Resolve IP address to hostname"""
			try:
				hostname, _, _ = gethostbyaddr(ip)
				return hostname
			except (herror, gaierror, timeout):
				return "Unknown"
			except Exception:
				return "Unknown"

		with app.app_context():
			results = {}
			start_time = time.time()

			try:
				# Start scan
				scan_type = 'auto' if is_auto_scan else 'manual'
				socketio.emit('scan_started', {
					'status': f'Starting {scan_type} network scan',
					'scan_type': scan_type
				})

				if network_range is None or network_range == 'auto':
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
					'total': total_hosts,
					'scan_type': scan_type
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
						progress = (completed / total_hosts) * 40  # First 40% of progress

						socketio.emit('scan_progress', {
							'phase': 'ping_sweep',
							'message': f'Ping sweep: {completed}/{total_hosts}',
							'progress': progress,
							'total': total_hosts,
							'current_ip': ip_str,
							'status': 'online' if is_online else 'offline',
							'scan_type': scan_type
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
								results[ip] = {'status': 'online', 'ports': [], 'hostname': 'Unknown'}
							else:
								results[ip] = {'status': 'offline', 'ports': [], 'hostname': 'Unknown'}
						except Exception:
							continue

				# Port scanning and hostname resolution
				if online_hosts:
					socketio.emit('scan_progress', {
						'phase': 'port_scan',
						'message': f'Starting port scan and hostname resolution of {len(online_hosts)} online hosts',
						'progress': 40,
						'total': len(online_hosts),
						'online_hosts': len(online_hosts),
						'scan_type': scan_type
					})

					completed_ports = 0

					def scan_ports_and_hostname(ip):
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
							time.sleep(0.01)

						# Get hostname
						hostname = get_hostname_from_ip(ip)

						completed_ports += 1
						progress = 40 + (completed_ports / len(online_hosts)) * 60  # Last 60%

						socketio.emit('scan_progress', {
							'phase': 'port_scan',
							'message': f'Port scan: {completed_ports}/{len(online_hosts)}',
							'progress': progress,
							'total': len(online_hosts),
							'current_ip': ip,
							'hostname': hostname,
							'open_ports': open_ports,
							'scan_type': scan_type
						})

						return ip, open_ports, hostname

					with ThreadPoolExecutor(max_workers=self.threads) as executor:
						futures = [executor.submit(scan_ports_and_hostname, ip) for ip in online_hosts]

						for future in as_completed(futures):
							try:
								ip, open_ports, hostname = future.result()
								results[ip]['ports'] = open_ports
								results[ip]['hostname'] = hostname
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
					'scan_type': scan_type,
					'summary': {
						'total_hosts': len(host_ips),
						'online_hosts': len(online_hosts),
						'hosts_with_ports': sum(1 for host in results.values() if len(host["ports"]) > 0)
					}
				})

				return results

			except Exception as e:
				socketio.emit('scan_error', {
					'error': str(e),
					'scan_type': scan_type
				})
				return results

scanner = WebsocketNetworkScan()

def auto_scan_worker():
	"""Worker thread for automatic scanning"""
	global auto_scan_running, next_auto_scan_time

	while auto_scan_running:
		try:
			# Get configuration
			interval_minutes = int(config.return_var("auto_scan", "interval_minutes"))
			network_range = config.return_var("auto_scan", "network_range")
			notes = config.return_var("auto_scan", "notes")

			# Update next scan time
			next_auto_scan_time = datetime.now() + timedelta(minutes=interval_minutes)

			# Emit auto scan scheduled notification
			with app.app_context():
				socketio.emit('auto_scan_scheduled', {
					'next_scan_time': next_auto_scan_time.isoformat(),
					'interval_minutes': interval_minutes
				})

			print(f"Starting automatic scan at {datetime.now()}")

			# Perform the scan
			scanner.combined_scan_web(
				app=app,
				network_range=network_range if network_range != 'auto' else None,
				notes=f"{notes} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
				is_auto_scan=True
			)

			print(f"Automatic scan completed. Next scan at {next_auto_scan_time}")

			# Wait for the interval
			time.sleep(interval_minutes * 60)

		except Exception as e:
			print(f"Error in auto scan worker: {e}")
			time.sleep(60)

def start_auto_scan():
	"""Start automatic scanning if enabled"""
	global auto_scan_thread, auto_scan_running

	if config.return_var("auto_scan", "enabled").lower() == "true":
		if auto_scan_thread is None or not auto_scan_thread.is_alive():
			auto_scan_running = True
			auto_scan_thread = threading.Thread(target=auto_scan_worker, daemon=True)
			auto_scan_thread.start()
			print("Automatic scanning started")
			return True
	return False

def stop_auto_scan():
	"""Stop automatic scanning"""
	global auto_scan_running
	auto_scan_running = False
	print("Automatic scanning stopped")

@app.route('/')
def health_check():
	return {
		'status': 'healthy',
		'service': 'network-scanner-backend',
		'version': '1.0.0',
		'auto_scan_enabled': config.return_var("auto_scan", "enabled").lower() == "true",
		'auto_scan_running': auto_scan_running,
		'next_auto_scan': next_auto_scan_time.isoformat() if next_auto_scan_time else None
	}

@app.route('/health')
def health():
	return {'status': 'ok'}

@socketio.on('connect')
def handle_connect():
	print('Client connected')
	emit('connected', {'status': 'Connected to scan server'})

	# Send auto scan status
	if auto_scan_running and next_auto_scan_time:
		emit('auto_scan_status', {
			'enabled': True,
			'running': True,
			'next_scan_time': next_auto_scan_time.isoformat(),
			'interval_minutes': int(config.return_var("auto_scan", "interval_minutes"))
		})

@socketio.on('disconnect')
def handle_disconnect():
	print('Client disconnected')

@socketio.on('start_scan')
def handle_start_scan(data):
	network_range = data.get('network_range', None)
	notes = data.get('notes', 'Manual WebSocket Scan')

	# Pass the app instance as the first argument
	socketio.start_background_task(target=scanner.combined_scan_web,
								   app=app,
								   network_range=network_range,
								   notes=notes,
								   is_auto_scan=False)

@socketio.on('get_scan_history')
def handle_get_scan_history():
	history = db.get_scan_history()
	emit('scan_history', history)

@socketio.on('get_statistics')
def handle_get_statistics():
	stats = db.get_statistics()
	emit('statistics', stats)

@socketio.on('get_auto_scan_status')
def handle_get_auto_scan_status():
	emit('auto_scan_status', {
		'enabled': config.return_var("auto_scan", "enabled").lower() == "true",
		'running': auto_scan_running,
		'next_scan_time': next_auto_scan_time.isoformat() if next_auto_scan_time else None,
		'interval_minutes': int(config.return_var("auto_scan", "interval_minutes"))
	})

@socketio.on('toggle_auto_scan')
def handle_toggle_auto_scan(data):
	"""Toggle automatic scanning on/off"""
	action = data.get('action', 'toggle')

	if action == 'start':
		success = start_auto_scan()
		emit('auto_scan_toggled', {
			'running': auto_scan_running,
			'success': success
		})
	elif action == 'stop':
		stop_auto_scan()
		emit('auto_scan_toggled', {
			'running': auto_scan_running,
			'success': True
		})

@app.route('/socket.io.js')
def socket_io_js():
	"""Serve Socket.IO client library"""
	return redirect('https://cdn.socket.io/4.8.1/socket.io.min.js')

if __name__ == "__main__":
	print("Starting Flask-SocketIO server...")

	# Start automatic scanning if enabled
	start_auto_scan()

	socketio.run(
		app,
		debug=True,
		host='0.0.0.0',
		port=5050,
		allow_unsafe_werkzeug=True
	)