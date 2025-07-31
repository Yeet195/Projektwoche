import subprocess
import configparser
import os
import sys
from typing import Dict, Optional
import re

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
        docker_indicators = [
            os.path.exists('/.dockerenv'),
            os.path.exists('/proc/1/cgroup') and any('docker' in line for line in open('/proc/1/cgroup', 'r').readlines()),
            os.environ.get('DOCKER_CONTAINER') == 'true',
            os.path.exists('/app') and os.getcwd().startswith('/app')
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
    
    def normalize_version(self, version_str: str) -> str:
        """
        Normalize version string to semantic version format
        Handles various git tag formats like v1.2.3, 1.2.3, etc.
        """
        if not version_str:
            return "0.0.0"
        
        # Remove 'v' prefix if present
        clean_version = version_str.lstrip('v')
        
        # If it looks like a commit hash (40 chars, hex), convert to 0.0.0+hash
        if re.match(r'^[a-f0-9]{40}$', clean_version):
            return f"0.0.0+{clean_version[:12]}"
        
        # Try to extract semantic version from string
        semver_pattern = r'(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9\-\.]+))?(?:\+([a-zA-Z0-9\-\.]+))?'
        match = re.match(semver_pattern, clean_version)
        
        if match:
            major, minor, patch, prerelease, build = match.groups()
            result = f"{major}.{minor}.{patch}"
            if prerelease:
                result += f"-{prerelease}"
            if build:
                result += f"+{build}"
            return result
        
        # Try to extract major.minor format and add .0
        simple_pattern = r'(\d+)\.(\d+)$'
        match = re.match(simple_pattern, clean_version)
        if match:
            major, minor = match.groups()
            return f"{major}.{minor}.0"
        
        # Try to extract just major and add .0.0
        major_pattern = r'(\d+)$'
        match = re.match(major_pattern, clean_version)
        if match:
            major = match.group(1)
            return f"{major}.0.0"
        
        # If nothing matches, treat as development version
        return f"0.0.0+{clean_version}"
    
    def compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two version strings using packaging.version
        Returns: -1 if version1 < version2, 0 if equal, 1 if version1 > version2
        """
        try:
            v1 = version.parse(self.normalize_version(version1))
            v2 = version.parse(self.normalize_version(version2))
            
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
            else:
                return 0
        except Exception as e:
            print(f"Error comparing versions {version1} and {version2}: {e}")
            return 0
    
    def get_latest_tag_local(self) -> Optional[str]:
        """Get latest git tag from local repository"""
        try:
            # Fetch tags first
            subprocess.check_output(
                ['git', 'fetch', '--tags'],
                cwd=os.path.dirname(self.config_file),
                timeout=30,
                stderr=subprocess.DEVNULL
            )
            
            # Get latest tag by version (semantic sorting)
            result = subprocess.check_output(
                ['git', 'tag', '-l', '--sort=-version:refname'],
                cwd=os.path.dirname(self.config_file),
                universal_newlines=True,
                timeout=10,
                stderr=subprocess.DEVNULL
            ).strip()
            
            if result:
                # Return the first (latest) tag
                tags = result.split('\n')
                return tags[0] if tags[0] else None
            return None
            
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return None
    
    def get_current_tag_local(self) -> Optional[str]:
        """Get current git tag if HEAD is on a tagged commit"""
        try:
            result = subprocess.check_output(
                ['git', 'describe', '--exact-match', '--tags', 'HEAD'],
                cwd=os.path.dirname(self.config_file),
                universal_newlines=True,
                timeout=10,
                stderr=subprocess.DEVNULL
            ).strip()
            return result
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return None
    
    def get_current_commit_local(self) -> Optional[str]:
        """Get current commit hash from local git"""
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
    
    def fetch_remote_tags_docker(self):
        """
        For Docker: fetch latest tag and all tags from GitHub API
        Returns: (latest_tag, all_tags_list)
        """
        try:
            import urllib.request
            import json
            
            repo_url = self.get_config_repo_url()
            if not repo_url or 'github.com/' not in repo_url:
                return None, None

            parts = repo_url.split('github.com/')[-1].rstrip('.git').split('/')
            if len(parts) >= 2:
                owner, repo = parts[0], parts[1]
                
                # Get all tags
                api_url = f"https://api.github.com/repos/{owner}/{repo}/tags"
                
                req = urllib.request.Request(api_url)
                req.add_header('User-Agent', 'NetworkScanner/1.0')
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    
                    if not data:
                        return None, None
                    
                    # Extract tag names
                    tag_names = [tag['name'] for tag in data]
                    
                    # Sort tags by semantic version
                    try:
                        sorted_tags = sorted(tag_names, 
                                           key=lambda x: version.parse(self.normalize_version(x)), 
                                           reverse=True)
                        latest_tag = sorted_tags[0] if sorted_tags else None
                        return latest_tag, tag_names
                    except Exception:
                        # Fallback to first tag if sorting fails
                        return tag_names[0], tag_names
            
            return None, None
            
        except Exception as e:
            print(f"Error fetching remote tags: {e}")
            return None, None
    
    def get_config_version(self) -> Optional[str]:
        """Get version from config.ini (can be tag or commit hash)"""
        try:
            return self.config.get('version', 'version')
        except (configparser.NoSectionError, configparser.NoOptionError):
            return None
    
    def get_config_minimum_version(self) -> Optional[str]:
        """Get minimum required version from config.ini"""
        try:
            return self.config.get('version', 'minimum_version')
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
    
    def check_version_status(self) -> Dict[str, any]:
        """
        Check version status using git tags with semantic versioning
        """
        result = {
            'is_docker': self.is_docker,
            'is_git_repo': False,
            'config_version': None,
            'minimum_version': None,
            'current_version': None,
            'latest_version': None,
            'is_up_to_date': None,
            'meets_minimum': None,
            'version_comparison': None,
            'status_message': '',
            'error': None,
            'repo_url': self.get_config_repo_url(),
            'branch': self.get_config_branch(),
            'available_tags': []
        }

        result['config_version'] = self.get_config_version()
        result['minimum_version'] = self.get_config_minimum_version()
        
        if self.is_docker:
            # Docker environment
            result['current_version'] = result['config_version']
            result['status_message'] = "Running in Docker container"
            
            # Fetch remote tags
            latest_tag, all_tags = self.fetch_remote_tags_docker()
            result['latest_version'] = latest_tag
            result['available_tags'] = all_tags or []
            
            if latest_tag:
                # Compare current vs latest
                comparison = self.compare_versions(result['current_version'], latest_tag)
                result['version_comparison'] = comparison
                
                if comparison >= 0:
                    result['is_up_to_date'] = True
                    result['status_message'] = "Docker image is up to date"
                else:
                    result['is_up_to_date'] = False
                    result['status_message'] = f"Docker image is outdated (current: {self.normalize_version(result['current_version'])}, latest: {self.normalize_version(latest_tag)})"
                
                # Check minimum version requirement
                if result['minimum_version']:
                    min_comparison = self.compare_versions(result['current_version'], result['minimum_version'])
                    result['meets_minimum'] = min_comparison >= 0
                    if not result['meets_minimum']:
                        result['status_message'] += f" - Below minimum required version {self.normalize_version(result['minimum_version'])}"
                else:
                    result['meets_minimum'] = True
            else:
                result['status_message'] = "Docker container (unable to check remote versions)"
                result['error'] = "Could not fetch remote versions"
                result['meets_minimum'] = True  # Assume OK if can't check
        
        else:
            # Local development environment
            try:
                subprocess.check_output(
                    ['git', 'rev-parse', '--git-dir'],
                    cwd=os.path.dirname(self.config_file),
                    stderr=subprocess.DEVNULL
                )
                result['is_git_repo'] = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                result['status_message'] = "Not a git repository or git not available"
                result['error'] = "Git not available"
                return result

            # Try to get current tag first
            current_tag = self.get_current_tag_local()
            if current_tag:
                result['current_version'] = current_tag
                result['status_message'] = f"On tagged version {self.normalize_version(current_tag)}"
            else:
                # Fall back to commit hash
                current_commit = self.get_current_commit_local()
                if current_commit:
                    result['current_version'] = current_commit
                    result['status_message'] = f"On commit {current_commit[:12]} (not tagged)"
                else:
                    result['error'] = "Could not determine current version"
                    result['status_message'] = "Unable to check git status"
                    return result

            # Get latest tag
            latest_tag = self.get_latest_tag_local()
            result['latest_version'] = latest_tag
            
            if latest_tag:
                if current_tag:
                    # Compare tags
                    comparison = self.compare_versions(current_tag, latest_tag)
                    result['version_comparison'] = comparison
                    
                    if comparison >= 0:
                        result['is_up_to_date'] = True
                        result['status_message'] = f"On latest version {self.normalize_version(current_tag)}"
                    else:
                        result['is_up_to_date'] = False
                        result['status_message'] = f"Behind latest version (current: {self.normalize_version(current_tag)}, latest: {self.normalize_version(latest_tag)})"
                else:
                    # On commit, not tag
                    result['is_up_to_date'] = False
                    result['status_message'] = f"On untagged commit, latest tag is {self.normalize_version(latest_tag)}"
                
                # Check minimum version requirement
                if result['minimum_version']:
                    current_for_min_check = current_tag or current_commit
                    min_comparison = self.compare_versions(current_for_min_check, result['minimum_version'])
                    result['meets_minimum'] = min_comparison >= 0
                    if not result['meets_minimum']:
                        result['status_message'] += f" - Below minimum required version {self.normalize_version(result['minimum_version'])}"
                else:
                    result['meets_minimum'] = True
            else:
                result['error'] = "No tags found in repository"
                result['status_message'] = "No version tags available"
                result['meets_minimum'] = True  # Assume OK if no tags
        
        return result
    
    def print_version_status(self):
        """Print a formatted version status message"""
        status = self.check_version_status()
        
        print("=" * 70)
        print("VERSION CHECK")
        print("=" * 70)
        
        print(f"Environment: {'Docker Container' if status['is_docker'] else 'Local Development'}")
        
        if status['repo_url']:
            print(f"Repository: {status['repo_url']}")
            print(f"Branch: {status['branch']}")
        
        if status['current_version']:
            if len(status['current_version']) == 40:  # Commit hash
                print(f"Current Version: {status['current_version'][:12]}... (commit)")
            else:
                print(f"Current Version: {self.normalize_version(status['current_version'])}")
        
        if status['latest_version']:
            print(f"Latest Version:  {self.normalize_version(status['latest_version'])}")
        
        if status['minimum_version']:
            print(f"Minimum Required: {self.normalize_version(status['minimum_version'])}")
            print(f"Meets Minimum: {'✓ Yes' if status['meets_minimum'] else '✗ No'}")
        
        print(f"Up to Date: {'✓ Yes' if status['is_up_to_date'] else '✗ No'}")
        print(f"Status: {status['status_message']}")
        
        if status['available_tags'] and len(status['available_tags']) > 0:
            print(f"Available Versions: {len(status['available_tags'])} tags found")
            # Show last 5 versions
            recent_tags = status['available_tags'][:5]
            for tag in recent_tags:
                print(f"  - {self.normalize_version(tag)}")
            if len(status['available_tags']) > 5:
                print(f"  ... and {len(status['available_tags']) - 5} more")
        
        if status['error']:
            print(f"Note: {status['error']}")
        
        print("=" * 70)
    
    def is_version_compatible(self, required_version: str) -> bool:
        """
        Check if current version is compatible with required version
        """
        status = self.check_version_status()
        
        if not status['current_version']:
            return False
        
        return self.compare_versions(status['current_version'], required_version) >= 0

def check_startup_version():
    """
    Convenience function to check version on startup
    Returns dict with version status info
    """
    try:
        checker = GitVersionChecker()
        status = checker.check_version_status()
        checker.print_version_status()
        
        # Return useful info for startup logic
        return {
            'is_up_to_date': status['is_up_to_date'],
            'meets_minimum': status['meets_minimum'],
            'current_version': status['current_version'],
            'latest_version': status['latest_version'],
            'minimum_version': status['minimum_version'],
            'is_docker': status['is_docker'],
            'error': status['error']
        }
    except Exception as e:
        print(f"Version check failed: {e}")
        return {
            'is_up_to_date': None,
            'meets_minimum': None,
            'current_version': None,
            'latest_version': None,
            'minimum_version': None,
            'is_docker': False,
            'error': str(e)
        }

def check_docker_version_compatibility(required_version: str) -> bool:
    """
    Standalone function to check if Docker version meets requirements
    Useful for installation scripts
    """
    try:
        checker = GitVersionChecker()
        return checker.is_version_compatible(required_version)
    except Exception:
        return False

if __name__ == "__main__":
    # Example usage
    check_startup_version()