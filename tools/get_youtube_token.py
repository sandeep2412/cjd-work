"""
Run ONCE on your own computer to connect YouTube.
  1. Put the client_secret.json you downloaded from Google Cloud next to this file.
  2. pip install google-auth-oauthlib
  3. python get_youtube_token.py
A browser opens -> pick the CJD YouTube channel -> Allow.
Copy the 3 printed values into GitHub secrets. Then DELETE client_secret.json from your PC folder (never upload it).
"""
import json, pathlib
from google_auth_oauthlib.flow import InstalledAppFlow
try:  # use the Windows certificate store (needed when antivirus scans HTTPS, e.g. Avast)
    import truststore; truststore.inject_into_ssl()
except ImportError: pass

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]
here = pathlib.Path(__file__).parent
secret = next(iter(here.glob("client_secret*.json")), None)
if not secret: raise SystemExit("client_secret.json not found next to this script")

flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
cfg = json.loads(secret.read_text())
cfg = cfg.get("installed") or cfg.get("web")
print("\nAdd these 3 GitHub secrets:\n")
print("YT_CLIENT_ID     =", cfg["client_id"])
print("YT_CLIENT_SECRET =", cfg["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
