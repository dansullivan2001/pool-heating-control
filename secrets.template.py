# secrets.template.py
#
# This is a template for secrets.py, which is NOT committed to the repository.
#
# To restore from this template:
#   1. Copy this file and rename the copy to secrets.py
#   2. Fill in the values below with your actual credentials
#   3. Deploy secrets.py to the Pico — it is never uploaded via OTA,
#      so it must be copied manually using mpremote or Thonny
#
# secrets.py is listed in .gitignore and must never be committed.
#
__version__ = "0.0.1"

# ==== Wi-Fi credentials ====
WIFI_SSID     = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

# Uncomment and fill in a second network (e.g. mobile hotspot for testing):
# WIFI_SSID     = "YOUR_HOTSPOT_SSID"
# WIFI_PASSWORD = "YOUR_HOTSPOT_PASSWORD"


# ==== Adafruit IO credentials ====
# Sign in at https://io.adafruit.com and find your key under My Key
AIO_USERNAME = "YOUR_AIO_USERNAME"
AIO_KEY      = "YOUR_AIO_KEY"


# ==== OTA manifest URL ====
# Raw GitHub URL to manifest.json on the main branch of your fork/repo
OTA_MANIFEST_URL = "https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME/main/manifest.json"
