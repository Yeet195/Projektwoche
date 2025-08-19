import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional


class NetworkScanDB:
    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.db_path = os.path.join(base_dir, "network_scans.db")
        else:
            self.db_path = db_path
        self.init_database()

    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    network_range TEXT,
                    total_hosts INTEGER,
                    online_hosts INTEGER,
                    scan_duration REAL,
                    notes TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scan_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id INTEGER,
                    ip_address TEXT NOT NULL,
                    hostname TEXT,
                    status TEXT NOT NULL,
                    open_ports TEXT,  -- JSON string of port list
                    scan_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (scan_id) REFERENCES scans (id)
                )
            ''')

            cursor.execute("PRAGMA table_info(scan_results)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'hostname' not in columns:
                cursor.execute('ALTER TABLE scan_results ADD COLUMN hostname TEXT')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_scan_results_ip 
                ON scan_results (ip_address)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_scan_results_scan_id 
                ON scan_results (scan_id)
            ''')

            conn.commit()

    def save_scan_results(self, results: Dict, network_range: str = None,
                          scan_duration: float = 0, notes: str = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            total_hosts = len(results)
            online_hosts = sum(1 for host in results.values() if host["status"] == "online")

            cursor.execute('''
                INSERT INTO scans (network_range, total_hosts, online_hosts, scan_duration, notes)
                VALUES (?, ?, ?, ?, ?)
            ''', (network_range, total_hosts, online_hosts, scan_duration, notes))

            scan_id = cursor.lastrowid

            for ip, data in results.items():
                ports_json = json.dumps(data["ports"]) if data["ports"] else "[]"
                hostname = data.get("hostname", "Unknown")
                cursor.execute('''
                    INSERT INTO scan_results (scan_id, ip_address, hostname, status, open_ports)
                    VALUES (?, ?, ?, ?, ?)
                ''', (scan_id, ip, hostname, data["status"], ports_json))

            conn.commit()
            return scan_id

    def get_scan_history(self, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, scan_date, network_range, total_hosts, online_hosts, 
                       scan_duration, notes
                FROM scans 
                ORDER BY scan_date DESC 
                LIMIT ?
            ''', (limit,))

            scans = []
            for row in cursor.fetchall():
                scans.append({
                    "scan_id": row[0],
                    "scan_date": row[1],
                    "network_range": row[2],
                    "total_hosts": row[3],
                    "online_hosts": row[4],
                    "scan_duration": row[5],
                    "notes": row[6]
                })

            return scans

    def get_scan_results(self, scan_id: int) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT scan_date, network_range, total_hosts, online_hosts, 
                       scan_duration, notes
                FROM scans 
                WHERE id = ?
            ''', (scan_id,))

            scan_info = cursor.fetchone()
            if not scan_info:
                return {}

            cursor.execute('''
                SELECT ip_address, hostname, status, open_ports, scan_timestamp
                FROM scan_results 
                WHERE scan_id = ?
                ORDER BY ip_address
            ''', (scan_id,))

            results = {}
            for row in cursor.fetchall():
                ip, hostname, status, ports_json, timestamp = row
                ports = json.loads(ports_json) if ports_json else []
                results[ip] = {
                    "status": status,
                    "ports": ports,
                    "hostname": hostname or "Unknown",
                    "timestamp": timestamp
                }

            return {
                "scan_info": {
                    "scan_date": scan_info[0],
                    "network_range": scan_info[1],
                    "total_hosts": scan_info[2],
                    "online_hosts": scan_info[3],
                    "scan_duration": scan_info[4],
                    "notes": scan_info[5]
                },
                "results": results
            }

    def get_host_history(self, ip_address: str, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.scan_date, sr.hostname, sr.status, sr.open_ports, s.network_range, sr.scan_id
                FROM scan_results sr
                JOIN scans s ON sr.scan_id = s.id
                WHERE sr.ip_address = ?
                ORDER BY s.scan_date DESC
                LIMIT ?
            ''', (ip_address, limit))

            history = []
            for row in cursor.fetchall():
                scan_date, hostname, status, ports_json, network_range, scan_id = row
                ports = json.loads(ports_json) if ports_json else []
                history.append({
                    "scan_date": scan_date,
                    "hostname": hostname or "Unknown",
                    "status": status,
                    "ports": ports,
                    "network_range": network_range,
                    "scan_id": scan_id
                })

            return history

    def get_online_hosts(self, scan_id: Optional[int] = None) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if scan_id is None:

                cursor.execute('SELECT MAX(id) FROM scans')
                result = cursor.fetchone()
                if not result or not result[0]:
                    return []
                scan_id = result[0]

            cursor.execute('''
                SELECT ip_address, hostname, open_ports, scan_timestamp
                FROM scan_results 
                WHERE scan_id = ? AND status = 'online'
                ORDER BY ip_address
            ''', (scan_id,))

            hosts = []
            for row in cursor.fetchall():
                ip, hostname, ports_json, timestamp = row
                ports = json.loads(ports_json) if ports_json else []
                hosts.append({
                    "ip": ip,
                    "hostname": hostname or "Unknown",
                    "ports": ports,
                    "timestamp": timestamp
                })

            return hosts

    def delete_old_scans(self, days_to_keep: int = 30):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM scan_results 
                WHERE scan_id IN (
                    SELECT id FROM scans 
                    WHERE scan_date < datetime('now', '-{} days')
                )
            '''.format(days_to_keep))

            cursor.execute('''
                DELETE FROM scans 
                WHERE scan_date < datetime('now', '-{} days')
            '''.format(days_to_keep))

            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count

    def get_statistics(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM scans')
            total_scans = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(DISTINCT ip_address) FROM scan_results')
            unique_ips = cursor.fetchone()[0]

            cursor.execute('SELECT MAX(scan_date) FROM scans')
            last_scan = cursor.fetchone()[0]

            cursor.execute('SELECT AVG(online_hosts) FROM scans')
            avg_online = cursor.fetchone()[0] or 0

            return {
                "total_scans": total_scans,
                "unique_ips_scanned": unique_ips,
                "last_scan_date": last_scan,
                "average_online_hosts": round(avg_online, 2)
            }