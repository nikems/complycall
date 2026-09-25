# Publish ComplyCall on a public link

Goal: a web address like `https://complycall.onrender.com` that anyone can open
from any PC — even when your Mac is off.

The app already includes everything needed to deploy:
`requirements.txt` (with gunicorn), `Procfile`, and `render.yaml`.

---

## Recommended: deploy on Render (free to start)

You need two free accounts: **GitHub** (to hold the code) and **Render** (to run it).

### Step 1 — Put the code on GitHub
1. Create a free account at github.com.
2. Click **New repository** → name it `complycall` → **Create**.
3. On the new repo page, click **uploading an existing file**.
4. Drag in the **contents of the `call_audit_pipeline` folder** (the `pipeline/`,
   `webapp/`, `requirements.txt`, `Procfile`, `render.yaml`, etc.) → **Commit changes**.

### Step 2 — Deploy on Render
1. Create a free account at render.com and click **New → Web Service**.
2. Connect your GitHub and pick the `complycall` repo.
3. Render reads `render.yaml` automatically. If it asks, confirm:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn --chdir webapp --bind 0.0.0.0:$PORT --timeout 180 app:app`
   - **Plan:** Free
4. Click **Create Web Service** and wait 2–4 minutes.
5. You get a public link like `https://complycall.onrender.com`. Done — share it.

The demo and `.txt` transcript upload work immediately, with **no keys**.

### Step 3 (optional) — turn on audio + Claude
In Render → your service → **Environment**, add:
- `ELEVENLABS_API_KEY` = your key (only needed to process audio)
- `ANTHROPIC_API_KEY`  = your key (better extraction than the no-API mode)
Save; Render redeploys automatically.

> Free plan note: the service **sleeps after ~15 min idle**; the first visit after
> that takes ~30 s to wake. Uploaded reports are not kept permanently. Both are fine
> for demos; for heavy use pick a paid plan.

---

## Fastest, temporary alternative — a tunnel (no accounts)
While the app runs on your Mac (`python app.py`), in another Terminal:
```bash
brew install cloudflared
cloudflared tunnel --url http://127.0.0.1:8001
```
It prints a public `https://…trycloudflare.com` link. Works only while your Mac is
on and the command is running. Good for a quick live demo.

---

## Important before sharing publicly
- **No login yet:** anyone with the link can use the app. For a public demo, use only
  the **demo data**, not real customer recordings.
- **Real personal data online** needs a proper GDPR review (legal basis, access control,
  data retention) — talk to your DPO before processing real calls on a public server.
- Keep your **API keys** only in the host's Environment settings — never inside the code
  or the GitHub repo.
