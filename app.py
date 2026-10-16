"""Vercel's WSGI entry point; desktop scripts keep their existing imports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from web_server import app  # noqa: E402,F401
