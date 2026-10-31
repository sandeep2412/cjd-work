# CJD Autopost: free daily posting bot

Posts the daily Creative Java Developers package automatically:

| Platform | What | Default time (IST) |
|---|---|---|
| LinkedIn company page | 4–5 infographics + captions | 9:00, 11:00, 17:00, 18:00, 19:00 |
| Instagram | 2 reels | 13:00, 19:00 |
| YouTube | same 2 reels as Shorts | 13:00, 19:00 |
| YouTube | 1 full video + thumbnail | 18:00 |

Every post carries its own time in `posts.json`, so you can change slots any day.

**Cost: ₹0.** It runs on GitHub Actions, which is free and unlimited for public repos, and uses each platform's official free API.

---

## How it works

```
Claude makes the day's files + posts.json
        │
        ▼
You create a GitHub Release named  queue-2026-11-01  and drag the files in   (1 minute)
        │
        ▼
Every 15 min the bot checks: anything due? → posts it → records it in state/posted.json
        │
        ▼
When the whole day is posted, the release is deleted automatically
```

* Nothing posts twice. Every posted item is recorded.
* If a platform fails, it retries 2 more times (15 min apart), then stops and shows the error.
* If LinkedIn isn't connected yet, the bot skips LinkedIn and tells you to post it by hand. Everything else still runs.
* GitHub's timer can start **5–20 minutes late**. That's normal.

---

## One-time setup (about 1–2 hours)

> Keep every key, token and secret **only** in GitHub Secrets. Never paste them into a file in the repo. The repo is public.

### Step 1: GitHub (10 min)

1. Create a free account at github.com, then click **New repository**.
   - Name: `cjd-autopost`
   - Visibility: **Public**. Instagram has to fetch the video from a public link, and public repos get unlimited free Actions minutes.
2. Click **uploading an existing file** and drag in everything from this folder, **including the `.github` folder**. Commit.
   - If `.github` doesn't upload, use **Add file → Create new file**, type `.github/workflows/autopost.yml` as the name, and paste that file's contents.
3. Go to **Settings → Actions → General → Workflow permissions**, choose **Read and write permissions**, and Save.
4. Open the **Actions** tab. If it asks, click **I understand… enable workflows**.

You'll add secrets in **Settings → Secrets and variables → Actions → New repository secret**.

### Step 2: YouTube (20 min + Google's audit)

1. Go to https://console.cloud.google.com, click **New project** and name it `CJD Autopost`.
2. Open **APIs & Services → Library → YouTube Data API v3** and click **Enable**.
3. Open **APIs & Services → OAuth consent screen**:
   - User type: **External**
   - App name: CJD Autopost
   - Your email as support and developer contact
   - Add yourself (the channel owner's Google account) as a **Test user**
   - Then go to **Publishing status** and click **PUBLISH APP** to move it to "In production".

   > ⚠️ Don't skip "Publish app". In *Testing* mode, Google expires the login after **7 days** and the bot stops. You don't need Google's verification for your own use; you'll just see an "unverified app" warning. Click **Advanced → Go to CJD Autopost**.
4. Open **Credentials → Create credentials → OAuth client ID → Desktop app**, then click **Download JSON**.
5. On your PC:
   - Put that JSON next to `tools/get_youtube_token.py`.
   - Run `pip install google-auth-oauthlib`, then `python get_youtube_token.py`.
   - In the browser, pick the **CJD channel** and click **Allow**.
   - Add the 3 printed values as GitHub secrets: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.
   - Delete the JSON file afterwards.
6. **Submit Google's audit:** search "YouTube API Services Audit and Quota Extension Form" and fill it in.
   - Use: "Uploading our own educational videos to our own channel on a schedule."
   - Until Google approves it (usually a few weeks), API uploads are **forced to Private**. The bot still uploads them, and you can switch them to Public in YouTube Studio with one click.
7. Custom thumbnails need a verified channel (phone verification in YouTube Studio).

### Step 3: Instagram (30 min)

1. In the Instagram app, go to **Settings → Account type** and switch to **Professional (Business or Creator)**.
2. Link Instagram to a **Facebook Page**. You can create a CJD page if you don't have one. Do this in Meta Business Suite, or under Instagram → Settings → **Accounts Center** / **Linked accounts**.
3. At https://developers.facebook.com, click **My Apps → Create app** and choose type **Business** (or "Other → Business").
   - You don't need App Review, because you're an admin of the app and it only posts to your own account.
4. Open https://developers.facebook.com/tools/explorer:
   - Select your app, then **Get User Access Token**.
   - Tick: `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, `business_management`.
   - Click **Generate**, allow everything, and copy the token.
5. Find your **App ID** and **App Secret** in your app under **App settings → Basic**.
6. On your PC, run `pip install requests`, then `python tools/get_meta_token.py`. Paste the three values when asked.
   - It prints `IG_USER_ID` and `IG_ACCESS_TOKEN` and should say **expires: never**. Add both as GitHub secrets.

### Step 4: LinkedIn company page (apply now, connect when approved)

1. At https://developer.linkedin.com, click **Create app**.
   - Name: CJD Autopost
   - LinkedIn Page: **Creative Java Developers**
   - Upload your logo.
2. On the **Settings** tab, click **Verify** next to the page, and approve the request as page admin.
3. On the **Products** tab, request **Community Management API**. LinkedIn wants this to be the *only* product on the app, so don't add others. Fill in the form:
   - Use case: "Scheduling and publishing our own educational posts to our company page."
   - Give honest company details.
4. Wait for approval (days to weeks). **Until then the bot leaves LinkedIn for you.** Schedule those posts in LinkedIn's built-in scheduler (the clock icon next to *Post*).
5. After approval:
   - On the **Auth** tab, add the redirect URL `http://localhost:8765/callback`.
   - Run `python tools/get_linkedin_token.py`.
   - Add these secrets: `LI_CLIENT_ID`, `LI_CLIENT_SECRET`, `LI_ACCESS_TOKEN`, `LI_REFRESH_TOKEN` (if printed) and `LI_ORG_ID` (your page number).
6. Repeat 5 **about once a year**, when the login expires. If no `LI_REFRESH_TOKEN` was printed, it's **every 60 days** instead. The bot's error message tells you when.
7. ⚠️ When you first add the LinkedIn secrets, make sure no LinkedIn posts you already scheduled by hand are still waiting in a queue release. Otherwise the bot posts them too.

### Step 5: Test everything

Go to **Actions → CJD Autopost → Run workflow → mode: check**. You should see ✅ for each connected platform. A platform you haven't connected yet shows ➖.

---

## Daily routine (1 minute)

Claude gives you a folder for each day containing the videos, images, covers and `posts.json`.

1. In your repo, go to **Releases → Draft a new release**.
2. **Choose a tag** → type `queue-2026-11-01` (use that day's date) → **Create new tag**.
3. Drag **all files from the folder** (including `posts.json`) into the box.
4. Click **Publish release**. A draft won't post.

That's it. Watch it work under **Actions**. Each run shows a summary with links to the live posts.

You can queue several days ahead. Just make one release per day.

### Changing something after upload
* **Before it posts:** edit the release. Delete the old `posts.json` and upload a fixed one, or swap a file.
* **To post something again:** give it a new `id` in `posts.json`.
* **To stop everything:** go to **Actions → CJD Autopost → ⋯ → Disable workflow**.

---

## posts.json format

```json
{ "posts": [
  { "id": "li-1", "platform": "linkedin", "time": "2026-11-01 09:00",
    "file": "CJD_LinkedIn_immutable.png", "caption": "Why is String immutable…  #Java" },

  { "id": "ig-1", "platform": "instagram", "time": "2026-11-01 13:00",
    "file": "reel1_1080.mp4", "cover": "reel1_cover.jpg", "caption": "…" },

  { "id": "yt-short-1", "platform": "youtube", "short": true, "time": "2026-11-01 13:00",
    "file": "reel1_4K.mp4", "title": "… #Shorts", "description": "…", "tags": ["java"] },

  { "id": "yt-video", "platform": "youtube", "time": "2026-11-01 18:00",
    "file": "video_4K.mp4", "thumbnail": "thumb.png", "title": "…", "description": "…",
    "tags": ["java"], "playlist_id": "optional" }
]}
```

Rules the bot checks before posting:
* Times are **IST**.
* Instagram needs **1080×1920 MP4** for reels and **JPG** (not PNG) for images and covers, and at most **5 hashtags**.
* YouTube titles must be 100 characters or less, with no `<` or `>`.
* LinkedIn posts take images only.

Claude runs `python autopost.py --validate posts.json` before handing you each day's folder.

## Optional settings (Settings → Secrets and variables → Actions → **Variables**)
| Variable | Default | Use |
|---|---|---|
| `LI_VERSION` | 202606 | LinkedIn API version (YYYYMM). Set a recent month if LinkedIn says the version is inactive. |
| `GRAPH_VERSION` | v23.0 | Facebook/Instagram API version |
| `KEEP_RELEASES` | (off) | `true` keeps finished releases instead of deleting them |

## Troubleshooting
| Message | Fix |
|---|---|
| ⚠️ YouTube kept this video private | The audit (Step 2.6) isn't approved yet. Make the video Public in YouTube Studio. |
| YouTube `invalid_grant` | The consent screen is still in *Testing*. Publish the app (Step 2.3) and redo Step 2.5. |
| Instagram could not process the file | Use a 1080×1920 H.264 MP4 between 3 seconds and 15 minutes long. |
| LinkedIn 401 | The token expired. Redo Step 4.5. |
| LinkedIn 403 | The API isn't approved yet, or you aren't a page admin. |
| Nothing happens for hours | Check the Actions tab is enabled. GitHub pauses timers in repos with **no activity for 60 days**, but the bot's own history commits keep it active. |
