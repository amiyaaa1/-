from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROFILE_DIR = DATA_DIR / "profiles"
COOKIE_DIR = DATA_DIR / "cookies"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
COOKIE_DIR.mkdir(parents=True, exist_ok=True)

HEADLESS = os.getenv("SANDBOX_HEADLESS", "true").lower() != "false"
CHROME_BINARY = os.getenv("SANDBOX_CHROME_BINARY")
