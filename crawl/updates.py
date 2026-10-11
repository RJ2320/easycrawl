"""Check the tracked Git branch without changing project files or installing updates."""
import os
import subprocess
from pathlib import Path


def update_available(root):
    root = Path(root)
    if not (root / ".git").exists():
        return False
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    def git(*args):
        result = subprocess.run(["git", *args], cwd=root, env=env, capture_output=True,
                                text=True, timeout=12,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        result.check_returncode()
        return result.stdout.strip()
    try:
        upstream = git("rev-parse", "--abbrev-ref", "@{upstream}")
        remote = git("config", "--get", "branch." + git("symbolic-ref", "--short", "HEAD") + ".remote")
        git("fetch", "--quiet", remote)
        return int(git("rev-list", "--count", "HEAD.." + upstream)) > 0
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def latest_release(current_version, platform=None):
    """Return a newer stable release with an installer for the current platform."""
    import json
    import re
    import sys
    platform = platform or sys.platform
    import urllib.request
    import certifi
    import ssl
    def version(text):
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text)
        return tuple(map(int, match.groups())) if match else None
    try:
        request = urllib.request.Request(
            "https://api.github.com/repos/RJ2320/easycrawl/releases/latest",
            headers={"User-Agent": "EasyCrawl", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=12, context=ssl.create_default_context(cafile=certifi.where())) as response:
            release = json.load(response)
        candidate = version(release.get("tag_name", ""))
        installed = version(current_version)
        if not candidate or not installed or candidate <= installed or release.get("prerelease") or release.get("draft"):
            return None
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            url = asset.get("browser_download_url", "")
            matches = ((platform == "win32" and name.startswith("EasyCrawl-Setup-") and name.endswith("-windows.exe"))
                       or (platform == "darwin" and name.startswith("EasyCrawl-") and name.endswith("-mac.dmg")))
            if (matches
                    and url.startswith("https://github.com/RJ2320/easycrawl/releases/download/")):
                return release["tag_name"], url
    except (OSError, ValueError, TypeError):
        pass
    return None
