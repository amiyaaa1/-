"""High-level package for automating the Kiro sign-in workflow."""

from .config_manager import ConfigManager, AppConfig
from .orchestrator import AutomationOrchestrator

__all__ = ["ConfigManager", "AppConfig", "AutomationOrchestrator"]
