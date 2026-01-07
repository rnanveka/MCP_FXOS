"""
Settings - Central configuration loader.

Loads configuration from:
1. Environment variables (.env file)
2. YAML config files (pipelines.yml, channels.yml)
3. Default values

Usage:
    from config.settings import Settings
    
    settings = Settings()
    print(settings.jenkins_base_url)
    print(settings.get_pipeline("FXOS_PB"))
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv


# Load .env file
load_dotenv()


@dataclass
class JenkinsSettings:
    """Jenkins configuration."""
    base_url: str = ""
    user: str = ""
    api_token: str = ""
    job_path_fxos_pb: str = ""
    job_path_asa: str = ""
    
    @classmethod
    def from_env(cls) -> "JenkinsSettings":
        """Load from environment variables."""
        return cls(
            base_url=os.getenv("JENKINS_BASE_URL", ""),
            user=os.getenv("JENKINS_USER", ""),
            api_token=os.getenv("JENKINS_API_TOKEN", ""),
            job_path_fxos_pb=os.getenv("JENKINS_JOB_PATH_FXOS_PB", ""),
            job_path_asa=os.getenv("JENKINS_JOB_PATH_ASA", "")
        )


@dataclass
class SplunkSettings:
    """Splunk configuration."""
    host: str = ""
    token: str = ""
    
    @classmethod
    def from_env(cls) -> "SplunkSettings":
        """Load from environment variables."""
        return cls(
            host=os.getenv("SPLUNK_HOST", ""),
            token=os.getenv("SPLUNK_TOKEN", "")
        )


@dataclass
class SwarmSettings:
    """Swarm configuration."""
    base_url: str = ""
    api_token: str = ""
    
    @classmethod
    def from_env(cls) -> "SwarmSettings":
        """Load from environment variables."""
        return cls(
            base_url=os.getenv("SWARM_BASE_URL", ""),
            api_token=os.getenv("SWARM_API_TOKEN", "")
        )


@dataclass
class WebexSettings:
    """Webex Bot configuration."""
    bot_token: str = ""
    webhook_secret: str = ""
    bot_email: str = ""
    
    @classmethod
    def from_env(cls) -> "WebexSettings":
        """Load from environment variables."""
        return cls(
            bot_token=os.getenv("WEBEX_BOT_TOKEN", ""),
            webhook_secret=os.getenv("WEBEX_WEBHOOK_SECRET", ""),
            bot_email=os.getenv("WEBEX_BOT_EMAIL", "")
        )


@dataclass
class ServerSettings:
    """Server configuration."""
    bot_port: int = 5000
    mcp_server_port: int = 8080
    debug: bool = False
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls) -> "ServerSettings":
        """Load from environment variables."""
        return cls(
            bot_port=int(os.getenv("BOT_PORT", "5000")),
            mcp_server_port=int(os.getenv("MCP_SERVER_PORT", "8080")),
            debug=os.getenv("DEBUG", "false").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "INFO")
        )


class Settings:
    """Central settings manager."""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize settings.
        
        Args:
            config_dir: Path to config directory (defaults to ./config)
        """
        self.config_dir = config_dir or Path(__file__).parent
        
        # Load environment settings
        self.jenkins = JenkinsSettings.from_env()
        self.splunk = SplunkSettings.from_env()
        self.swarm = SwarmSettings.from_env()
        self.webex = WebexSettings.from_env()
        self.server = ServerSettings.from_env()
        
        # Load YAML configs
        self._pipelines: Dict[str, Any] = {}
        self._channels: Dict[str, Any] = {}
        
        self._load_yaml_configs()
    
    def _load_yaml_configs(self) -> None:
        """Load YAML configuration files."""
        # Load pipelines.yml
        pipelines_file = self.config_dir / "pipelines.yml"
        if pipelines_file.exists():
            with open(pipelines_file) as f:
                self._pipelines = yaml.safe_load(f) or {}
        
        # Load channels.yml
        channels_file = self.config_dir / "channels.yml"
        if channels_file.exists():
            with open(channels_file) as f:
                self._channels = yaml.safe_load(f) or {}
    
    # Convenience properties
    @property
    def jenkins_base_url(self) -> str:
        return self.jenkins.base_url
    
    @property
    def jenkins_user(self) -> str:
        return self.jenkins.user
    
    @property
    def jenkins_token(self) -> str:
        return self.jenkins.api_token
    
    @property
    def splunk_host(self) -> str:
        return self.splunk.host
    
    @property
    def splunk_token(self) -> str:
        return self.splunk.token
    
    @property
    def webex_token(self) -> str:
        return self.webex.bot_token
    
    # Pipeline methods
    def get_pipeline(self, name: str) -> Optional[Dict[str, Any]]:
        """Get pipeline configuration by name."""
        pipelines = self._pipelines.get("pipelines", [])
        for p in pipelines:
            if p.get("name") == name:
                return p
        return None
    
    def get_enabled_pipelines(self) -> List[Dict[str, Any]]:
        """Get all enabled pipelines."""
        pipelines = self._pipelines.get("pipelines", [])
        return [p for p in pipelines if p.get("enabled", True)]
    
    # Channel methods
    def get_webex_rooms(self) -> List[Dict[str, Any]]:
        """Get enabled Webex rooms."""
        rooms = self._channels.get("webex", {}).get("rooms", [])
        return [r for r in rooms if r.get("enabled", False) and r.get("roomId")]
    
    def get_webex_people(self) -> List[Dict[str, Any]]:
        """Get enabled Webex people."""
        people = self._channels.get("webex", {}).get("people", [])
        return [p for p in people if p.get("enabled", False) and p.get("email")]


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
