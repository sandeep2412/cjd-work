"""
Run AFTER LinkedIn approves "Community Management API" for your app.
  1. In your LinkedIn app -> Auth tab -> Authorized redirect URLs, add:  http://localhost:8765/callback
  2. pip install requests
  3. python get_linkedin_token.py
A browser opens -> sign in as a PAGE ADMIN -> Allow.
Prints the secrets to add to GitHub, plus the IDs of the company pages you administer.
Re-run this about once a year (when the refresh token expires).
"""
import http.server, secrets, urllib.parse, webbrowser, requests
try:  # use the Windows certificate store (needed when antivirus scans HTTPS, e.g. Avast)
    import truststore; truststore.inject_into_ssl()
except ImportError: pass

PORT, VERSION = 8765, "202606"
REDIRECT = f"http://localhost:{PORT}/callback"
SCOPES = "w_organization_social r_organization_social rw_organization_admin"
cid = input("LinkedIn Client ID: ").strip()
csec = input("LinkedIn Client Secret: ").strip()
state, box = secrets.token_urlsafe(16), {}

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        box.update({k: v[0] for k, v in q.items()})
        self.send_response(200); self.end_headers()
        self.wfile.write(b"Done - you can close this tab and go back to the terminal.")
    def log_message(self, *a): pass

srv = http.server.HTTPServer(("localhost", PORT), H)
url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(
    dict(response_type="code", client_id=cid, redirect_uri=REDIRECT, state=state, scope=SCOPES))
print("Opening browser…  if it doesn't open, paste this link:\n", url)
webbrowser.open(url)
while "code" not in box and "error" not in box: srv.handle_request()
if box.get("error"): raise SystemExit(f"LinkedIn said: {box.get('error_description', box['error'])}")
if box.get("state") != state: raise SystemExit("state mismatch - try again")

tok = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data=dict(
    grant_type="authorization_code", code=box["code"], redirect_uri=REDIRECT, client_id=cid, client_secret=csec)).json()
if "access_token" not in tok: raise SystemExit(tok)
print("\nAdd these GitHub secrets:\n")
print("LI_CLIENT_ID     =", cid)
print("LI_CLIENT_SECRET =", csec)
print("LI_ACCESS_TOKEN  =", tok["access_token"], f"   (valid {tok.get('expires_in', 0) // 86400} days)")
if tok.get("refresh_token"):
    print("LI_REFRESH_TOKEN =", tok["refresh_token"], f"   (valid {tok.get('refresh_token_expires_in', 0) // 86400} days)")

h = {"Authorization": f"Bearer {tok['access_token']}", "LinkedIn-Version": VERSION, "X-Restli-Protocol-Version": "2.0.0"}
acl = requests.get("https://api.linkedin.com/rest/organizationAcls?q=roleAssignee&role=ADMINISTRATOR&state=APPROVED", headers=h).json()
print("\nCompany pages you administer (use the number as LI_ORG_ID):")
for e in acl.get("elements", []):
    print("  ", e.get("organization", "").split(":")[-1], " ", e.get("organization"))
if not acl.get("elements"):
    print("   (none found - you can also copy the number from your page admin URL: linkedin.com/company/<NUMBER>/admin)")
