#!/usr/bin/env python3
"""
CJD Autopost - posts the daily content queue to YouTube, Instagram and a LinkedIn company page.

Queue  : GitHub releases whose tag starts with "queue-". Each release holds the media files
         plus one posts.json that says what goes where and when (IST).
State  : state/posted.json in the repo (committed back by the workflow) so nothing posts twice.
Modes  : python autopost.py               -> post everything that is due
         python autopost.py --check       -> test every platform login, post nothing
         python autopost.py --validate F  -> check a posts.json (+ files next to it) before uploading
         DRY_RUN=1                        -> log what would be posted, post nothing
"""
import json, os, re, sys, time, tempfile, datetime as dt
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "state" / "posted.json"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
ENV = os.environ.get
DRY = ENV("DRY_RUN", "").lower() in ("1", "true", "yes")
GRAPH = f"https://graph.facebook.com/{ENV('GRAPH_VERSION') or 'v23.0'}"
LI_VERSION = ENV("LI_VERSION") or "202606"
MAX_TRIES = 3
TAG_PREFIX = "queue-"
SUMMARY = []

def log(*a): print(*a, flush=True)
def note(line): SUMMARY.append(line); log(line)

# ---------------------------------------------------------------- queue (GitHub releases)
class Queue:
    """One day's queue: posts + a way to fetch each file."""
    def __init__(self, tag, posts, files, release_id=None, local_dir=None):
        self.tag, self.posts, self.files, self.release_id, self.local_dir = tag, posts, files, release_id, local_dir

    def download(self, name, dest_dir):
        if self.local_dir: return str(Path(self.local_dir) / name)
        a = self.files[name]
        out = Path(dest_dir) / name
        with gh_session().get(a["url"], headers={"Accept": "application/octet-stream"}, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(out, "wb") as f:
                for chunk in r.iter_content(1 << 20): f.write(chunk)
        return str(out)

    def public_url(self, name, resolve=False):
        if self.local_dir: raise RuntimeError("Instagram needs a public URL - not available in local mode")
        url = self.files[name]["browser_download_url"]
        if resolve:  # follow GitHub's redirect to the signed storage URL
            r = requests.head(url, allow_redirects=False, timeout=30)
            url = r.headers.get("Location", url)
        return url

_gh = None
def gh_session():
    global _gh
    if _gh is None:
        _gh = requests.Session()
        _gh.headers.update({"Authorization": f"Bearer {ENV('GITHUB_TOKEN')}", "X-GitHub-Api-Version": "2022-11-28"})
    return _gh

def gh_api(path, method="GET", **kw):
    r = gh_session().request(method, f"https://api.github.com/repos/{ENV('GITHUB_REPOSITORY')}{path}", timeout=60, **kw)
    r.raise_for_status()
    return r.json() if r.content else None

def load_queues():
    if ENV("QUEUE_DIR"):  # local testing: QUEUE_DIR/<tag>/posts.json
        qs = []
        for pj in sorted(Path(ENV("QUEUE_DIR")).glob("*/posts.json")):
            qs.append(Queue(pj.parent.name, json.loads(pj.read_text(encoding="utf-8"))["posts"], {}, local_dir=pj.parent))
        return qs
    qs = []
    for rel in gh_api("/releases?per_page=50"):
        if not rel["tag_name"].startswith(TAG_PREFIX): continue
        if rel.get("draft"): note(f"⏸️ `{rel['tag_name']}` is still a draft - press Publish release so it can post"); continue
        files = {a["name"]: a for a in rel["assets"]}
        if "posts.json" not in files:
            note(f"⚠️ `{rel['tag_name']}` has no posts.json - skipped"); continue
        r = gh_session().get(files["posts.json"]["url"], headers={"Accept": "application/octet-stream"}, timeout=60)
        r.raise_for_status()
        try: posts = json.loads(r.content.decode("utf-8-sig"))["posts"]
        except Exception as e: note(f"❌ `{rel['tag_name']}` posts.json is not valid JSON: {e}"); continue
        qs.append(Queue(rel["tag_name"], posts, files, release_id=rel["id"]))
    return qs

def delete_release(q):
    if q.local_dir or DRY or ENV("KEEP_RELEASES", "").lower() in ("1", "true"): return
    gh_api(f"/releases/{q.release_id}", "DELETE")
    try: gh_api(f"/git/refs/tags/{q.tag}", "DELETE")
    except Exception: pass
    note(f"🧹 `{q.tag}` fully posted - release removed")

# ---------------------------------------------------------------- validation
PLATFORMS = ("youtube", "instagram", "linkedin")
def validate_posts(posts, available=None):
    errs, ids = [], set()
    for i, p in enumerate(posts):
        w = f"post #{i + 1} ({p.get('id', '?')})"
        for k in ("id", "platform", "time"):
            if not p.get(k): errs.append(f"{w}: missing '{k}'")
        if p.get("id") in ids: errs.append(f"{w}: duplicate id")
        ids.add(p.get("id"))
        if p.get("platform") not in PLATFORMS: errs.append(f"{w}: platform must be one of {PLATFORMS}")
        try: parse_time(p.get("time", ""))
        except Exception: errs.append(f"{w}: time must look like 2026-11-01 09:00")
        pl = p.get("platform")
        if pl == "youtube":
            if not p.get("file"): errs.append(f"{w}: youtube needs 'file'")
            if not p.get("title"): errs.append(f"{w}: youtube needs 'title'")
            if len(p.get("title", "")) > 100: errs.append(f"{w}: title over 100 characters")
            if re.search(r"[<>]", p.get("title", "") + p.get("description", "")): errs.append(f"{w}: YouTube rejects < or > in title/description")
            if len(p.get("description", "")) > 5000: errs.append(f"{w}: description over 5000 characters")
            if len(",".join(p.get("tags", []))) > 450: errs.append(f"{w}: tags too long (keep under ~450 characters total)")
        if pl == "instagram":
            if not p.get("file"): errs.append(f"{w}: instagram needs 'file'")
            if len(p.get("caption", "")) > 2200: errs.append(f"{w}: caption over 2200 characters")
            if len(re.findall(r"#\w+", p.get("caption", ""))) > 5: errs.append(f"{w}: more than 5 hashtags (Instagram's limit)")
            f = p.get("file", "").lower()
            if f and not f.endswith((".mp4", ".mov", ".jpg", ".jpeg")): errs.append(f"{w}: instagram file must be .mp4/.mov (reel) or .jpg (image - PNG is not accepted)")
            if p.get("cover", "").lower().endswith(".png"): errs.append(f"{w}: instagram cover must be .jpg")
        if pl == "linkedin":
            if not (p.get("caption") or p.get("file")): errs.append(f"{w}: linkedin needs 'caption' and/or 'file'")
            if len(p.get("caption", "")) > 3000: errs.append(f"{w}: caption over 3000 characters")
            if p.get("file") and not p["file"].lower().endswith((".png", ".jpg", ".jpeg", ".gif")): errs.append(f"{w}: linkedin supports image files only")
        if available is not None:
            for k in ("file", "cover", "thumbnail"):
                if p.get(k) and p[k] not in available: errs.append(f"{w}: file '{p[k]}' is not in the queue")
    return errs

def parse_time(s):
    s = s.strip().replace("T", " ")
    t = dt.datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
    return t.replace(tzinfo=IST)

# ---------------------------------------------------------------- YouTube
_yt = None
def youtube():
    global _yt
    if _yt is None:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        need("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
        creds = Credentials(None, refresh_token=ENV("YT_REFRESH_TOKEN"), token_uri="https://oauth2.googleapis.com/token",
                            client_id=ENV("YT_CLIENT_ID"), client_secret=ENV("YT_CLIENT_SECRET"))
        _yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    return _yt

def post_youtube(q, p, tmp):
    from googleapiclient.http import MediaFileUpload
    title, desc = p["title"], p.get("description", "")
    if p.get("short") and "#shorts" not in (title + desc).lower(): desc = (desc + "\n\n#Shorts").strip()
    body = {"snippet": {"title": title, "description": desc, "tags": p.get("tags", []), "categoryId": str(p.get("category", 27)),
                        "defaultLanguage": p.get("language", "en"), "defaultAudioLanguage": p.get("language", "en")},
            "status": {"privacyStatus": p.get("privacy", "public"), "selfDeclaredMadeForKids": False}}
    if DRY: return f"(dry run) would upload '{title}'"
    path = q.download(p["file"], tmp)
    req = youtube().videos().insert(part="snippet,status", body=body,
                                    media_body=MediaFileUpload(path, chunksize=32 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status: log(f"   upload {int(status.progress() * 100)}%")
    vid = resp["id"]
    if p.get("thumbnail") and not p.get("short"):
        try:
            youtube().thumbnails().set(videoId=vid, media_body=MediaFileUpload(yt_thumb(q.download(p["thumbnail"], tmp)))).execute()
        except Exception as e: note(f"   ⚠️ thumbnail not set ({e}) - set it in YouTube Studio")
    if p.get("playlist_id"):  # video is already live: a failure here must not trigger a re-upload
        try:
            youtube().playlistItems().insert(part="snippet", body={"snippet": {"playlistId": p["playlist_id"],
                                             "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        except Exception as e: note(f"   ⚠️ not added to playlist ({e}) - add it in YouTube Studio")
    if resp.get("status", {}).get("privacyStatus") != p.get("privacy", "public"):
        note("   ⚠️ YouTube kept this video private - your API project still needs Google's audit (see README step 2.6)")
    return f"https://youtu.be/{vid}"

def yt_thumb(path):
    """YouTube thumbnails must be under 2 MB -> 1280x720 JPEG."""
    from PIL import Image
    out = str(Path(path).with_suffix(".yt.jpg"))
    im = Image.open(path).convert("RGB")
    if im.width / im.height > 1.5: im = im.resize((1280, 720), Image.LANCZOS)
    else: im.thumbnail((1280, 1280), Image.LANCZOS)
    q = 92
    while True:
        im.save(out, "JPEG", quality=q, optimize=True)
        if os.path.getsize(out) < 1_900_000 or q < 50: return out
        q -= 8

# ---------------------------------------------------------------- Instagram (Graph API, Facebook-login token)
def ig(method, path, **params):
    params["access_token"] = ENV("IG_ACCESS_TOKEN")
    r = requests.request(method, f"{GRAPH}/{path}", data=params if method == "POST" else None,
                         params=params if method == "GET" else None, timeout=120)
    j = r.json()
    if "error" in j: raise RuntimeError(f"Instagram: {j['error'].get('message')}")
    return j

def post_instagram(q, p, tmp):
    need("IG_USER_ID", "IG_ACCESS_TOKEN")
    uid, f = ENV("IG_USER_ID"), p["file"].lower()
    is_video = f.endswith((".mp4", ".mov"))
    if DRY: return f"(dry run) would publish {'reel' if is_video else 'image'} {p['file']}"
    for attempt, resolve in enumerate((False, True)):
        args = dict(caption=p.get("caption", ""))
        if is_video:
            args.update(media_type="REELS", video_url=q.public_url(p["file"], resolve), share_to_feed="true")
            if p.get("cover"): args["cover_url"] = q.public_url(p["cover"], resolve)
        else:
            args["image_url"] = q.public_url(p["file"], resolve)
        cid = ig("POST", f"{uid}/media", **args)["id"]
        state = wait_ig(cid)
        if state == "FINISHED": break
        if attempt == 1: raise RuntimeError(f"Instagram could not process the file (status {state}). Reels must be 1080x1920 H.264 MP4, 3s-15min.")
        log("   retrying with direct storage URL…")
    mid = ig("POST", f"{uid}/media_publish", creation_id=cid)["id"]
    try: return ig("GET", mid, fields="permalink").get("permalink", mid)
    except Exception: return f"instagram media {mid}"  # already published: never let this trigger a repost

def wait_ig(cid, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = ig("GET", cid, fields="status_code,status")
        sc = j.get("status_code")
        if sc in ("FINISHED", "ERROR", "EXPIRED"):
            if sc != "FINISHED": log(f"   Instagram status: {j.get('status')}")
            return sc
        time.sleep(15)
    return "TIMEOUT"

# ---------------------------------------------------------------- LinkedIn (company page, Posts API)
_li_token = None
def li_token():
    global _li_token
    if _li_token: return _li_token
    if ENV("LI_REFRESH_TOKEN") and ENV("LI_CLIENT_ID") and ENV("LI_CLIENT_SECRET"):
        r = requests.post("https://www.linkedin.com/oauth/v2/accessToken", timeout=60, data=dict(
            grant_type="refresh_token", refresh_token=ENV("LI_REFRESH_TOKEN"),
            client_id=ENV("LI_CLIENT_ID"), client_secret=ENV("LI_CLIENT_SECRET")))
        if r.ok: _li_token = r.json()["access_token"]; return _li_token
        log(f"   LinkedIn refresh failed ({r.text[:200]}), trying LI_ACCESS_TOKEN")
    need("LI_ACCESS_TOKEN")
    _li_token = ENV("LI_ACCESS_TOKEN"); return _li_token

def li_headers():
    return {"Authorization": f"Bearer {li_token()}", "LinkedIn-Version": LI_VERSION,
            "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}

def li_text(s):
    """LinkedIn 'little text': escape reserved chars, turn #word into real hashtags."""
    out, i = [], 0
    for m in re.finditer(r"#(\w+)", s):
        out.append(re.sub(r"([\\|{}@\[\]()<>#*_~])", r"\\\1", s[i:m.start()]))
        out.append("{hashtag|\\#|" + m.group(1) + "}")
        i = m.end()
    out.append(re.sub(r"([\\|{}@\[\]()<>#*_~])", r"\\\1", s[i:]))
    return "".join(out)

def li_configured(): return bool(ENV("LI_ORG_ID") and (ENV("LI_ACCESS_TOKEN") or ENV("LI_REFRESH_TOKEN")))

def post_linkedin(q, p, tmp):
    need("LI_ORG_ID")
    org = f"urn:li:organization:{ENV('LI_ORG_ID')}"
    if DRY: return f"(dry run) would post to {org}: {p.get('caption', '')[:60]!r}"
    body = {"author": org, "commentary": li_text(p.get("caption", "")), "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
    if p.get("file"):
        r = requests.post("https://api.linkedin.com/rest/images?action=initializeUpload", headers=li_headers(),
                          json={"initializeUploadRequest": {"owner": org}}, timeout=60)
        li_check(r)
        v = r.json()["value"]
        with open(q.download(p["file"], tmp), "rb") as fh:
            up = requests.put(v["uploadUrl"], data=fh, headers={"Authorization": f"Bearer {li_token()}"}, timeout=300)
        li_check(up)
        body["content"] = {"media": {"id": v["image"], "altText": p.get("alt", p.get("title", "Java interview infographic"))[:4000]}}
    r = requests.post("https://api.linkedin.com/rest/posts", headers=li_headers(), json=body, timeout=60)
    li_check(r)
    urn = r.headers.get("x-restli-id", "")
    return f"https://www.linkedin.com/feed/update/{urn}/" if urn else "posted"

def li_check(r):
    if not r.ok:
        hint = ""
        if r.status_code == 401: hint = " (token expired - rerun tools/get_linkedin_token.py and update the secrets)"
        if r.status_code == 403: hint = " (no permission - is Community Management API approved and are you a page admin?)"
        if r.status_code == 426 or "version" in r.text.lower(): hint = " (LinkedIn-Version too old/new - set the LI_VERSION variable to a recent YYYYMM)"
        raise RuntimeError(f"LinkedIn {r.status_code}: {r.text[:300]}{hint}")

# ---------------------------------------------------------------- helpers
class NotConfigured(Exception): pass
def need(*keys):
    miss = [k for k in keys if not ENV(k)]
    if miss: raise NotConfigured(f"missing secret(s): {', '.join(miss)}")

POSTERS = {"youtube": post_youtube, "instagram": post_instagram, "linkedin": post_linkedin}

def load_state():
    try: return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception: return {"posted": {}, "failed": {}, "manual": {}}

def save_state(s):
    if DRY: return
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")

def write_summary():
    path = ENV("GITHUB_STEP_SUMMARY")
    if path and SUMMARY:
        with open(path, "a", encoding="utf-8") as f: f.write("\n".join(SUMMARY) + "\n")

# ---------------------------------------------------------------- main loop
def run():
    st = load_state()
    for k in ("posted", "failed", "manual"): st.setdefault(k, {})
    now = dt.datetime.now(IST)
    queues = load_queues()
    if not queues: log("Queue is empty."); return
    for q in queues:
        errs = validate_posts(q.posts, None if q.local_dir else set(q.files))
        if errs:
            note(f"❌ `{q.tag}` has problems, nothing in it will post until fixed:")
            for e in errs: note(f"   - {e}")
            continue
        pending = 0
        for p in sorted(q.posts, key=lambda p: parse_time(p["time"])):
            key = f"{q.tag}/{p['id']}"
            if key in st["posted"] or key in st["manual"]: continue
            if st["failed"].get(key, {}).get("tries", 0) >= MAX_TRIES: continue
            when = parse_time(p["time"])
            if when > now: pending += 1; continue
            if p["platform"] == "linkedin" and not li_configured():
                st["manual"][key] = {"at": now.isoformat(timespec="minutes")}
                note(f"✋ LinkedIn not connected yet - post **{p.get('file') or p['id']}** manually (was due {p['time']})")
                save_state(st); continue
            log(f"▶ {key} [{p['platform']}] due {p['time']}")
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    link = POSTERS[p["platform"]](q, p, tmp)
                    st["posted"][key] = {"at": dt.datetime.now(IST).isoformat(timespec="minutes"), "link": link}
                    st["failed"].pop(key, None)
                    note(f"✅ {p['platform']}: {p.get('title') or p.get('file') or p['id']} → {link}")
                except NotConfigured as e:
                    pending += 1  # not set up yet: keep it waiting, retry once the secrets exist
                    note(f"⛔ {p['platform']} not set up ({e}) - {p['id']} is waiting")
                except Exception as e:
                    f = st["failed"].setdefault(key, {"tries": 0})
                    f["tries"] += 1; f["error"] = str(e)[:500]
                    note(f"❌ {p['platform']} {p['id']} failed (try {f['tries']}/{MAX_TRIES}): {str(e)[:400]}")
                    if f["tries"] < MAX_TRIES: pending += 1
            save_state(st)
        if pending == 0 and not any(st["failed"].get(f"{q.tag}/{p['id']}", {}).get("tries", 0) >= MAX_TRIES
                                    and f"{q.tag}/{p['id']}" not in st["posted"] for p in q.posts):
            delete_release(q)

def check():
    ok = True
    def t(name, fn):
        nonlocal ok
        try: note(f"✅ {name}: {fn()}")
        except NotConfigured as e: note(f"➖ {name}: not set up yet ({e})")
        except Exception as e: ok = False; note(f"❌ {name}: {str(e)[:300]}")
    t("YouTube", lambda: youtube().channels().list(part="snippet", mine=True).execute()["items"][0]["snippet"]["title"])
    def igc():
        need("IG_USER_ID", "IG_ACCESS_TOKEN")
        j = ig("GET", ENV("IG_USER_ID"), fields="username")
        lim = ig("GET", f"{ENV('IG_USER_ID')}/content_publishing_limit", fields="quota_usage,config")
        d = (lim.get("data") or [{}])[0]
        return f"@{j['username']} (published today via API: {d.get('quota_usage', '?')}/{d.get('config', {}).get('quota_total', '?')})"
    t("Instagram", igc)
    def lic():
        need("LI_ORG_ID")
        r = requests.get(f"https://api.linkedin.com/rest/organizations/{ENV('LI_ORG_ID')}", headers=li_headers(), timeout=60)
        li_check(r); return r.json().get("localizedName", "ok")
    t("LinkedIn page", lic)
    if ENV("GITHUB_TOKEN"): t("Queue", lambda: f"{len(load_queues())} release(s) waiting")
    return ok

if __name__ == "__main__":
    try:
        if "--validate" in sys.argv:
            pj = Path(sys.argv[sys.argv.index("--validate") + 1])
            posts = json.loads(pj.read_text(encoding="utf-8-sig"))["posts"]
            errs = validate_posts(posts, {f.name for f in pj.parent.iterdir()})
            print("\n".join(errs) if errs else f"OK - {len(posts)} posts")
            for p in sorted(posts, key=lambda p: parse_time(p["time"])):
                print(f"  {p['time']}  {p['platform']:9}  {p.get('title') or p.get('file') or p['id']}")
            sys.exit(1 if errs else 0)
        if "--check" in sys.argv: sys.exit(0 if check() else 1)
        run()
    finally:
        write_summary()
