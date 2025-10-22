"""Entry point for executing the automation from the command line."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .config_manager import ConfigManager
from .logger import setup_logging
from .orchestrator import AutomationOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(description="Automate Kiro authentication flows")
    parser.add_argument(
        "--config",
        default=os.environ.get("KIRO_AUTOMATION_CONFIG", "config.toml"),
        help="Path to the TOML configuration file",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    config = ConfigManager(config_path).load()
    logger = setup_logging(config.logging)

    orchestrator = AutomationOrchestrator(config, logger=logger)
    orchestrator.run()


if __name__ == "__main__":  # pragma: no cover - executable entry point
    main()
