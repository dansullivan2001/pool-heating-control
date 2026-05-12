# ota.py
__version__ = "0.1.0"

"""
Over-the-air update manager for the Pico pool controller.

Flow
----
Triggered by MQTT → state["ota_pending"] = True → main.py calls check_for_update().

check_for_update()
  1. Fetch manifest.json from GitHub (fixed URL in secrets.OTA_MANIFEST_URL)
  2. Compare each file's local __version__ string against the manifest
  3. Download all changed files to <path>.new  (no files are touched yet)
  4. If ALL downloads succeed  → apply_updates() then machine.reset()
     If ANY download fails     → abort(), clean up .new files, return safely

apply_updates()
  For each file being replaced:
    - Rename existing file to <path>.bak  (backup)
    - Rename <path>.new    to <path>      (activate)
  ota.py is updated last so this module stays intact throughout.

On next boot, main.py calls verify_or_rollback() before anything else:
  - Check every critical file exists and compiles cleanly
  - If OK  → delete all .bak files (reclaim flash), continue normal boot
  - If NOT → restore every .bak that exists, reboot

Manifest format (manifest.json hosted at secrets.OTA_MANIFEST_URL)
-------------------------------------------------------------------
{
  "version": "2.1.0",
  "base_url": "https://raw.githubusercontent.com/USER/REPO/main/firmware",
  "files": {
    "main.py":                    "2.1.0",
    "state.py":                   "0.1.0",
    "config.py":                  "0.0.1",
    "ota.py":                     "0.1.0",
    "status_led.py":              "0.2.0",
    "utils.py":                   "0.0.1",
    "controller/controller.py":   "0.6.0",
    "sensors/__init__.py":        "0.1.0",
    "sensors/temperature.py":     "0.1.0",
    "sensors/water_level.py":     "0.1.0",
    "sensors/button.py":          "0.1.0",
    "network/__init__.py":        "0.1.0",
    "network/mqtt.py":            "0.5.0",
    "network/wifi.py":            "0.4.0",
    "network/feeds.py":           "0.4.0"
  }
}
"""

import os
import time
import gc

try:
    import urequests
    import machine
    ON_PICO = True
except ImportError:
    ON_PICO = False

try:
    import secrets
except ImportError:
    secrets = None


# -------------------------------------------------------------------------
# Files verified on every boot. If any fail, rollback is triggered.
# These are the minimum set needed to boot and run safely.
# -------------------------------------------------------------------------
CRITICAL_FILES = [
    "main.py",
    "state.py",
    "ota.py",
    "controller/controller.py",
    "network/__init__.py",
    "sensors/__init__.py",
]

# ota.py is applied last so this module stays valid throughout the update.
OTA_SELF = "ota.py"


# =========================================================================
# Boot-time: verify or rollback
# =========================================================================

def verify_or_rollback():
    """
    Call this at the very start of main.py, before any other imports.

    Checks that all critical files exist and compile without syntax errors.
    If any fail, restores .bak files and reboots.
    If all pass, deletes .bak files to reclaim flash space.

    Returns True if verification passed (normal boot can continue).
    Never returns False — a failed verification always reboots.
    """
    print("🔍 OTA: Verifying firmware integrity...")

    failed = []
    for path in CRITICAL_FILES:
        reason = _verify_file(path)
        if reason:
            print(f"  ❌ {path}: {reason}")
            failed.append(path)
        else:
            print(f"  ✅ {path}")

    if failed:
        print(f"⚠️ OTA: {len(failed)} file(s) failed verification — rolling back")
        _restore_backups()
        time.sleep(1)
        if ON_PICO:
            machine.reset()
        return False   # only reached in desktop testing

    # All good — clean up backups to free flash
    _delete_backups()
    print("✅ OTA: Firmware verified — normal boot")
    return True


def _verify_file(path):
    """
    Return None if the file exists and compiles, or an error string if not.
    Uses compile() for syntax checking without executing the file.
    """
    if not _exists(path):
        return "file missing"
    try:
        with open(path, "r") as f:
            source = f.read()
        compile(source, path, "exec")
        return None
    except SyntaxError as e:
        return f"syntax error: {e}"
    except Exception as e:
        return f"read error: {e}"


def _restore_backups():
    """Restore all .bak files found anywhere in the filesystem."""
    print("🔄 OTA: Restoring backups...")
    restored = 0
    for path in _find_bak_files():
        original = path[:-4]   # strip ".bak"
        try:
            if _exists(original):
                os.remove(original)
            os.rename(path, original)
            print(f"  ↩️  {original}")
            restored += 1
        except Exception as e:
            print(f"  ⚠️ Could not restore {original}: {e}")
    print(f"🔄 OTA: Restored {restored} file(s)")


def _delete_backups():
    """Delete all .bak files to reclaim flash space after a clean boot."""
    for path in _find_bak_files():
        try:
            os.remove(path)
        except Exception as e:
            print(f"⚠️ OTA: Could not delete {path}: {e}")


def _find_bak_files(root="."):
    """
    Walk the filesystem and return a list of all .bak file paths.
    MicroPython's os.listdir() doesn't recurse, so we do it manually.
    """
    results = []
    try:
        entries = os.listdir(root)
    except Exception:
        return results

    for name in entries:
        path = name if root == "." else f"{root}/{name}"
        if name.endswith(".bak"):
            results.append(path)
        else:
            # Try descending into directories
            try:
                sub = os.listdir(path)
                # If listdir succeeds it's a directory
                results.extend(_find_bak_files(path))
            except Exception:
                pass   # it's a file, not a directory

    return results


# =========================================================================
# MQTT-triggered: check for and apply updates
# =========================================================================

def check_for_update():
    """
    Main OTA entry point. Called by main.py when state["ota_pending"] is True.

    Downloads and applies any changed files. Reboots if updates were applied.
    Returns quietly if no updates are available or if anything goes wrong
    (the system continues running on the current firmware).
    """
    if not ON_PICO:
        print("ℹ️ OTA: Skipping — not running on Pico")
        return

    if secrets is None or not hasattr(secrets, "OTA_MANIFEST_URL"):
        print("⚠️ OTA: No OTA_MANIFEST_URL in secrets — skipping")
        return

    print("🔄 OTA: Checking for updates...")
    gc.collect()

    # 1. Fetch manifest
    manifest = _fetch_manifest()
    if manifest is None:
        print("⚠️ OTA: Could not fetch manifest — aborting")
        return

    base_url = manifest.get("base_url", "").rstrip("/")
    files    = manifest.get("files", {})

    if not base_url or not files:
        print("⚠️ OTA: Manifest missing base_url or files — aborting")
        return

    # 2. Determine which files need updating
    to_update = []
    for path, remote_ver in files.items():
        local_ver = _read_version(path)
        if local_ver != remote_ver:
            print(f"  🔄 {path}: {local_ver} → {remote_ver}")
            to_update.append((path, remote_ver, f"{base_url}/{path}"))
        else:
            print(f"  ✅ {path}: {local_ver} (current)")

    if not to_update:
        print("✅ OTA: Firmware is up to date")
        return

    # 3. Download all changed files to .new (nothing is replaced yet)
    print(f"📥 OTA: Downloading {len(to_update)} file(s)...")
    downloaded = []
    for path, remote_ver, url in to_update:
        gc.collect()
        if _download(path, url):
            downloaded.append(path)
        else:
            # One failure → abort entire update for consistency
            print(f"❌ OTA: Download failed for {path} — aborting update")
            _cleanup_new_files(downloaded)
            return

    # 4. All downloads succeeded — verify each .new file before applying
    print("🔍 OTA: Verifying downloaded files...")
    for path in downloaded:
        reason = _verify_file(path + ".new")
        if reason:
            print(f"❌ OTA: Verification failed for {path}.new: {reason} — aborting")
            _cleanup_new_files(downloaded)
            return

    # 5. Apply: rename .new → file (existing → .bak)
    #    Apply ota.py last so this module stays intact throughout.
    print("✅ OTA: All files verified — applying update...")
    apply_order = [p for p in downloaded if p != OTA_SELF]
    if OTA_SELF in downloaded:
        apply_order.append(OTA_SELF)

    for path in apply_order:
        _apply_one(path)

    print("🚀 OTA: Update applied — rebooting")
    time.sleep(1)
    machine.reset()


# =========================================================================
# Helpers
# =========================================================================

def _fetch_manifest():
    """Fetch and parse manifest.json from the server. Returns dict or None."""
    try:
        resp = urequests.get(secrets.OTA_MANIFEST_URL, timeout=10)
        data = resp.json()
        resp.close()
        return data
    except Exception as e:
        print(f"⚠️ OTA: Manifest fetch failed: {e}")
        return None


def _read_version(path):
    """
    Extract __version__ from a local file by scanning lines — does not exec
    the file, so it's safe even on large or partially-corrupt modules.
    Returns the version string, or None if not found or file absent.
    """
    if not _exists(path):
        return None
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("__version__"):
                    # Handles: __version__ = "1.2.3" or __version__ = '1.2.3'
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip().strip("\"'")
    except Exception as e:
        print(f"⚠️ OTA: Could not read version from {path}: {e}")
    return None


def _download(path, url):
    """
    Download url and save to <path>.new.
    Creates any missing parent directories first.
    Returns True on success.
    """
    temp_path = path + ".new"
    try:
        # Ensure parent directory exists
        _ensure_dir(path)

        resp = urequests.get(url, timeout=15)

        # Validate response
        if resp.status_code != 200:
            print(f"⚠️ OTA: HTTP {resp.status_code} for {url}")
            resp.close()
            return False

        data = resp.text
        resp.close()

        if not data:
            print(f"⚠️ OTA: Empty response for {url}")
            return False

        with open(temp_path, "w") as f:
            f.write(data)

        print(f"  📥 {path} ({len(data)} bytes)")
        return True

    except Exception as e:
        print(f"⚠️ OTA: Download failed for {path}: {e}")
        # Clean up partial file if it exists
        try:
            os.remove(temp_path)
        except Exception:
            pass
        return False


def _apply_one(path):
    """
    Atomically replace <path> with <path>.new, backing up the original to <path>.bak.
    """
    new_path = path + ".new"
    bak_path = path + ".bak"

    try:
        # Remove old backup if present
        if _exists(bak_path):
            os.remove(bak_path)
        # Back up current file
        if _exists(path):
            os.rename(path, bak_path)
        # Activate new file
        os.rename(new_path, path)
        print(f"  ✅ Applied {path}")
    except Exception as e:
        print(f"  ⚠️ OTA: Failed to apply {path}: {e}")


def _cleanup_new_files(paths):
    """Remove any .new files left over from a failed download run."""
    for path in paths:
        try:
            os.remove(path + ".new")
        except Exception:
            pass


def _ensure_dir(file_path):
    """Create parent directories for file_path if they don't exist."""
    parts = file_path.split("/")
    if len(parts) <= 1:
        return   # top-level file, no directory needed
    dir_path = ""
    for part in parts[:-1]:
        dir_path = part if not dir_path else f"{dir_path}/{part}"
        try:
            os.mkdir(dir_path)
        except OSError:
            pass   # already exists


def _exists(path):
    """Return True if path exists on the filesystem."""
    try:
        os.stat(path)
        return True
    except OSError:
        return False