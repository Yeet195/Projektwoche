import subprocess
import configparser
import os
import sys
from typing import Dict, Optional

class GitVersionChecker:
	def __init__(self, config_file: str = None):
		if config_file is None:
			current_dir = os.path.dirname(os.path.abspath(__file__))
			self.config_file = os.path.join(current_dir, 'config.ini')
		else:
			self.config_file = config_file
		
		self.config = self.load_config()
		self.is_docker = self.detect_docker_environment()
	
	def detect_docker_environment(self) -> bool:
		"""Detect if running in Docker container"""
		# Check for common Docker indicators
		docker_indicators = [
			os.path.exists('/.dockerenv'),
			os.path.exists('/proc/1/cgroup') and any('docker' in line for line in open('/proc/1/cgroup', 'r').readlines()),
			os.environ.get('DOCKER_CONTAINER') == 'true',
			os.path.exists('/app') and os.getcwd().startswith('/app')  # Common Docker working directory
		]
		return any(docker_indicators)
	
	def load_config(self) -> configparser.ConfigParser:
		"""Load configuration from config.ini"""
		config = configparser.ConfigParser()
		if os.path.exists(self.config_file):
			config.read(self.config_file)
		else:
			raise FileNotFoundError(f"Config file not found: {self.config_file}")
		return config
	
	def get_current_commit_local(self) -> Optional[str]:
		"""Get current commit hash from local git (for non-Docker)"""
		try:
			result = subprocess.check_output(
				['git', 'rev-parse', 'HEAD'],
				cwd=os.path.dirname(self.config_file),
				universal_newlines=True,
				timeout=10,
				stderr=subprocess.DEVNULL
			).strip()
			return result
		except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
			return None
	
	def get_remote_commit_local(self, branch: str = None) -> Optional[str]:
		"""Get latest commit hash from remote (for non-Docker)"""
		try:
			# First, try to fetch latest info from remote
			subprocess.check_output(
				['git', 'fetch'],
				cwd=os.path.dirname(self.config_file),
				timeout=30,
				stderr=subprocess.DEVNULL
			)
			
			# Get configured branch or use current branch
			if branch is None:
				branch = self.config.get('version', 'branch', fallback='main')
			
			# Get remote commit hash
			result = subprocess.check_output(
				['git', 'rev-parse', f'origin/{branch}'],
				cwd=os.path.dirname(self.config_file),
				universal_newlines=True,
				timeout=10,
				stderr=subprocess.DEVNULL
			).strip()
			return result
		except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
			return None
	
	def get_config_version(self) -> Optional[str]:
		"""Get version from config.ini"""
		try:
			return self.config.get('version', 'version')
		except (configparser.NoSectionError, configparser.NoOptionError):
			return None
	
	def get_config_repo_url(self) -> Optional[str]:
		"""Get repository URL from config.ini"""
		try:
			return self.config.get('version', 'repo')
		except (configparser.NoSectionError, configparser.NoOptionError):
			return None
	
	def get_config_branch(self) -> str:
		"""Get branch from config.ini"""
		try:
			return self.config.get('version', 'branch', fallback='main')
		except (configparser.NoSectionError, configparser.NoOptionError):
			return 'main'
	
	def fetch_remote_commit_docker(self) -> Optional[str]:
		"""
		For Docker: fetch latest commit from GitHub API
		This doesn't require git or cloning the repo
		"""
		try:
			import urllib.request
			import json
			
			repo_url = self.get_config_repo_url()
			if not repo_url:
				return None
			
			# Extract owner/repo from GitHub URL
			if 'github.com/' in repo_url:
				parts = repo_url.split('github.com/')[-1].rstrip('.git').split('/')
				if len(parts) >= 2:
					owner, repo = parts[0], parts[1]
					branch = self.get_config_branch()
					
					# GitHub API URL for latest commit
					api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
					
					req = urllib.request.Request(api_url)
					req.add_header('User-Agent', 'NetworkScanner/1.0')
					
					with urllib.request.urlopen(req, timeout=10) as response:
						data = json.loads(response.read().decode())
						return data['sha']
			
			return None
			
		except Exception:
			return None
	
	def check_version_status(self) -> Dict[str, any]:
		"""
		Check if the current version is up to date
		Returns a dictionary with version status information
		"""
		result = {
			'is_docker': self.is_docker,
			'is_git_repo': False,
			'config_version': None,
			'current_commit': None,
			'remote_commit': None,
			'is_up_to_date': None,
			'status_message': '',
			'error': None,
			'repo_url': self.get_config_repo_url(),
			'branch': self.get_config_branch()
		}
		
		# Get version from config
		result['config_version'] = self.get_config_version()
		
		if self.is_docker:
			# Docker environment - use config version and try to fetch remote
			result['current_commit'] = result['config_version']
			result['status_message'] = "Running in Docker container"
			
			# Try to fetch latest commit from GitHub API
			result['remote_commit'] = self.fetch_remote_commit_docker()
			
			if result['remote_commit']:
				if result['current_commit'] and result['current_commit'] == result['remote_commit']:
					result['is_up_to_date'] = True
					result['status_message'] = "Docker image is up to date"
				else:
					result['is_up_to_date'] = False
					result['status_message'] = "Docker image may be outdated"
			else:
				result['status_message'] = "Docker container (unable to check remote)"
				result['error'] = "Could not fetch remote version"
			
		else:
			# Local environment - use git commands
			try:
				# Check if we're in a git repository
				subprocess.check_output(
					['git', 'rev-parse', '--git-dir'],
					cwd=os.path.dirname(self.config_file),
					stderr=subprocess.DEVNULL
				)
				result['is_git_repo'] = True
			except (subprocess.CalledProcessError, FileNotFoundError):
				result['status_message'] = "Not a git repository or git not available"
				return result
			
			# Get current commit
			result['current_commit'] = self.get_current_commit_local()
			if not result['current_commit']:
				result['error'] = "Could not determine current commit"
				result['status_message'] = "Unable to check git status"
				return result
			
			# Get remote commit
			result['remote_commit'] = self.get_remote_commit_local()
			if not result['remote_commit']:
				result['error'] = "Could not fetch remote commit (network issue?)"
				result['status_message'] = "Unable to check remote version (offline?)"
				return result
			
			# Compare versions
			if result['current_commit'] == result['remote_commit']:
				result['is_up_to_date'] = True
				result['status_message'] = "Running on latest commit"
			else:
				result['is_up_to_date'] = False
				# Check if we're ahead or behind
				try:
					ahead_behind = subprocess.check_output(
						['git', 'rev-list', '--count', '--left-right', 
						 f"{result['remote_commit']}...{result['current_commit']}"],
						cwd=os.path.dirname(self.config_file),
						universal_newlines=True,
						timeout=10
					).strip().split('\t')
					
					behind = int(ahead_behind[0])
					ahead = int(ahead_behind[1])
					
					if behind > 0 and ahead == 0:
						result['status_message'] = f"Behind by {behind} commit(s)"
					elif ahead > 0 and behind == 0:
						result['status_message'] = f"⬆Ahead by {ahead} commit(s)"
					elif ahead > 0 and behind > 0:
						result['status_message'] = f"Diverged: {ahead} ahead, {behind} behind"
					else:
						result['status_message'] = "Version mismatch"
						
				except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
					result['status_message'] = "Not on latest commit"
		
		return result
	
	def print_version_status(self):
		"""Print a formatted version status message"""
		status = self.check_version_status()
		
		print("=" * 60)
		print("VERSION CHECK")
		print("=" * 60)
		
		print(f"Environment: {'Docker Container' if status['is_docker'] else 'Local Development'}")
		
		if status['repo_url']:
			print(f"Repository: {status['repo_url']}")
			print(f"Branch: {status['branch']}")
		
		if status['config_version']:
			print(f"Config Version: {status['config_version'][:12]}...")
		
		if status['current_commit']:
			print(f"Current Commit: {status['current_commit'][:12]}...")
		
		if status['remote_commit']:
			print(f"Remote Commit:  {status['remote_commit'][:12]}...")
		
		print(f"Status: {status['status_message']}")
		
		if status['error']:
			print(f"Note: {status['error']}")
		
		print("=" * 60)

def check_startup_version():
	"""
	Convenience function to check version on startup
	Returns True if up to date, False otherwise, None if cannot determine
	"""
	try:
		checker = GitVersionChecker()
		status = checker.check_version_status()
		checker.print_version_status()
		return status['is_up_to_date']
	except Exception as e:
		print(f"Version check failed: {e}")
		return None

if __name__ == "__main__":
	# For testing
	check_startup_version()