"""
Run ONCE to get a NON-EXPIRING Instagram token (no install needed except `pip install requests`).
You need: your Meta app's App ID + App Secret, and a short-lived User token from the
Graph API Explorer with these permissions:
  instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement, business_management
  python get_meta_token.py
"""
import requests

V = "v23.0"
G = f"https://graph.facebook.com/{V}"
app_id = input("App ID: ").strip()
app_secret = input("App Secret: ").strip()
short = input("Short-lived User token (from Graph API Explorer): ").strip()

r = requests.get(f"{G}/oauth/access_token", params=dict(grant_type="fb_exchange_token", client_id=app_id,
                                                         client_secret=app_secret, fb_exchange_token=short)).json()
if "error" in r: raise SystemExit(r["error"]["message"])
long_user = r["access_token"]

pages = requests.get(f"{G}/me/accounts", params=dict(access_token=long_user, fields="id,name,access_token,instagram_business_account")).json()
if "error" in pages: raise SystemExit(pages["error"]["message"])
found = False
for p in pages.get("data", []):
    ig = p.get("instagram_business_account")
    print(f"\nFacebook Page: {p['name']} ({p['id']})")
    if not ig:
        print("   no Instagram business account linked to this page"); continue
    found = True
    who = requests.get(f"{G}/{ig['id']}", params=dict(fields="username", access_token=p["access_token"])).json()
    exp = requests.get(f"{G}/debug_token", params=dict(input_token=p["access_token"], access_token=f"{app_id}|{app_secret}")).json()
    e = exp.get("data", {}).get("expires_at", "?")
    print(f"   Instagram: @{who.get('username')}   token expires: {'never' if e == 0 else e}")
    print("\n   Add these 2 GitHub secrets:")
    print("   IG_USER_ID      =", ig["id"])
    print("   IG_ACCESS_TOKEN =", p["access_token"])
if not found:
    print("\nNo Instagram account found. Make sure Instagram is a Professional (Business/Creator) account linked to the Facebook Page.")
