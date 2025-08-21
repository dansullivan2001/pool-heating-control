# ota.py
__version__ = "0.0.1"

import os
import time
import urequests  # or your preferred HTTP client
import machine
import secrets

# Track the modules we manage
MODULES = ["main.py", "pump.py", "sensors.py", "feeds.py", "ota.py", "utils.py", "config.py"]

def fetch_manifest():
    """Fetch the OTA manifest from the server (JSON with module:version)."""
    try:
        resp = urequests.get(secrets.OTA_MANIFEST_URL)
        manifest = resp.json()
        resp.close()
        return manifest
    except Exception as e:
        print("⚠️ OTA: Failed to fetch manifest:", e)
        return None

def get_local_version(module):
    """Return __version__ of a local module, or None."""
    try:
        loc = {}
        with open(module) as f:
            exec(f.read(), loc)
        return loc.get("__version__", None)
    except:
        return None

def download_module(module, url):
    """Download module to a temporary .new file."""
    try:
        resp = urequests.get(url)
        data = resp.text
        resp.close()
        temp_file = module + ".new"
        with open(temp_file, "w") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"⚠️ OTA: Failed to download {module}: {e}")
        return False

def apply_updates():
    """Atomically replace old modules with new ones, keep backup."""
    for module in MODULES:
        new_file = module + ".new"
        if os.path.exists(new_file):
            backup_file = module + ".bak"
            if os.path.exists(module):
                os.rename(module, backup_file)      # Backup old
            os.rename(new_file, module)             # Replace with new
            print(f"✅ OTA: Updated {module}")

def check_for_update():
    """Main OTA check routine."""
    manifest = fetch_manifest()
    if not manifest:
        return

    updates_needed = False
    for module in MODULES:
        remote_ver = manifest.get(module)
        local_ver = get_local_version(module)
        if remote_ver and remote_ver != local_ver:
            print(f"🔄 OTA: {module} update available ({local_ver} -> {remote_ver})")
            url = f"{manifest['base_url']}/{module}"
            if download_module(module, url):
                updates_needed = True

    if updates_needed:
        print("🚀 OTA: Applying updates and rebooting...")
        apply_updates()
        time.sleep(1)
        machine.reset()  # soft reboot

def rollback_if_needed():
    """Optional: Restore backups if main modules fail verification."""
    # Example: check critical module exists
    for module in ["main.py", "pump.py"]:
        if not os.path.exists(module):
            print(f"⚠️ OTA: {module} missing! Restoring backup.")
            backup_file = module + ".bak"
            if os.path.exists(backup_file):
                os.rename(backup_file, module)
    # Could also reboot here if needed
