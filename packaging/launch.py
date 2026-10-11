"""Entry point for the packaged app (PyInstaller runs this as a plain script)."""
import sys

from crawl.ui.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
