"""Loopback-only LinkedIn companion for the Firebase website."""
import os

os.environ["JOB_FINDER_CONNECTOR"] = "1"
from web_server import app


if __name__ == "__main__":
    print("LinkedIn connector ready for https://jobs-tool.web.app")
    print("Select 'Use this computer for LinkedIn' on the website.")
    print("Keep this process running. Press Ctrl+C to stop.")
    app.run(host="127.0.0.1", port=8765)
