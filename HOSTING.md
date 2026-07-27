# Put the site online (auto-updating, view from anywhere)

This hosts your site as a web link that **updates itself daily in the cloud** — open the
URL on any computer or phone, always current, laptop can be off.

Everything on your side is a **one-time setup**. I've already prepared the automation
(`.github/workflows/refresh.yml`) and initialized this folder as a git repo with a first commit.

---

## Step 1 — Make a free GitHub account (skip if you have one)
Go to **https://github.com** → Sign up. Free tier is all you need.

## Step 2 — Create an empty repository
1. Click the **+** (top-right) → **New repository**.
2. Name it `mlb-matchups` (any name is fine).
3. **Public** (it's just baseball numbers — nothing sensitive).
4. Do **NOT** check "Add a README" / .gitignore / license — leave it empty.
5. Click **Create repository**.

GitHub will show a page with a URL like `https://github.com/YOURNAME/mlb-matchups.git`. Copy it.

## Step 3 — Push this folder up
Open a terminal in this folder (`C:\Users\brick\mlb-compare`) and run these four lines,
replacing the URL with yours from Step 2:

```bash
git remote add origin https://github.com/YOURNAME/mlb-matchups.git
git branch -M main
git push -u origin main
```

The first push pops a browser window to sign in to GitHub — approve it (Git for Windows
handles this automatically). That's the only login you'll do.

## Step 4 — Turn on the website
In your repo on github.com:
1. **Settings** → **Pages** (left sidebar).
2. Under "Build and deployment" → **Source: Deploy from a branch**.
3. Branch: **main**, folder: **/ (root)** → **Save**.

Wait ~1–2 minutes. Your site is live at:
**`https://YOURNAME.github.io/mlb-matchups/`** — bookmark that on every device.

## Step 5 — Let the daily robot update it
1. **Settings** → **Actions** → **General** (left sidebar).
2. Scroll to **Workflow permissions** → select **Read and write permissions** → **Save**.

That's it. The cloud now refreshes your data every morning (~10am & ~1pm ET) and the
site updates itself — no laptop required.

---

## Using it day to day
- **Just open the bookmark** on any device. It's always current.
- **Force a refresh now:** repo → **Actions** tab → **Refresh MLB data** → **Run workflow**.
- **Your local `refresh.bat` still works** for offline use. If you tweak the site files
  (index.html etc.) on your laptop, push the changes so the web copy matches:
  ```bash
  git add -A && git commit -m "update site" && git push
  ```

## If something looks stale
- Repo → **Actions** tab shows every run. A red ✗ means a data source hiccuped (usually
  Baseball Savant being flaky). The site keeps the last good data — it never overwrites
  with garbage. Re-run it manually (Step: "Force a refresh now").
