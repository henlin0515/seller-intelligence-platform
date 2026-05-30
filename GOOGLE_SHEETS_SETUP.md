# Google Sheets Service Account Setup (Seller Dashboard)

This guide configures **private** access to your **mirror** Google Sheet for SHP EDU. The AI Assistant is unchanged. Live sheet loading is **not** enabled until you approve the next phase.

**Mirror spreadsheet (do not use the company tracker):**

`https://docs.google.com/spreadsheets/d/1uhq7vJqLSDbckeLHf2SxEjEloMHb-xLa8YimGCs9Eyk`

---

## What was added in the codebase

| Path | Purpose |
|------|---------|
| `seller/google_sheets/config.py` | Reads env vars; no hardcoded secrets |
| `seller/google_sheets/auth.py` | Builds Service Account credentials (file or inline JSON) |
| `seller/google_sheets/client.py` | gspread client placeholder (`ping`, tab list — not wired to dashboard) |
| `seller/google_sheets/status.py` | `get_integration_status()` for configuration checks |
| `credentials/` | Local folder for your JSON key (gitignored) |

Dashboard data still comes from **`seller/raw_data.py` (mock)** until `GOOGLE_SHEETS_ENABLED=true` and the merge/cache phase is approved.

---

## 1. Google Cloud — manual steps

Do these in [Google Cloud Console](https://console.cloud.google.com/).

### 1.1 Create or select a project

1. Open **Google Cloud Console** → top bar **Select a project**.
2. **New Project** (e.g. `shp-edu-dashboard`) or pick an existing one.
3. Note the **Project ID** (for your own records).

### 1.2 Enable Google Sheets API

1. **APIs & Services** → **Library**.
2. Search **Google Sheets API**.
3. Click **Enable**.

(Optional but recommended for future metadata: enable **Google Drive API** — same project, **Library** → **Google Drive API** → **Enable**. gspread may use Drive scope for some operations; readonly Sheets scope is enough for read-only mirror access.)

### 1.3 Create a Service Account

1. **APIs & Services** → **Credentials**.
2. **Create credentials** → **Service account**.
3. Name: e.g. `shp-edu-sheets-reader`.
4. **Create and continue** (roles optional for sheet shared directly to the SA — see 1.4).
5. **Done**.

### 1.4 Create a JSON key

1. Open the service account you created → **Keys** tab.
2. **Add key** → **Create new key** → **JSON** → **Create**.
3. A `.json` file downloads — **keep it secret**.

From that file you need:

- `client_email` — e.g. `shp-edu-sheets-reader@your-project.iam.gserviceaccount.com`
- `private_key`, `project_id`, etc. (the app loads the full JSON)

### 1.5 Share the mirror sheet with the Service Account

1. Open your **mirror** spreadsheet (link above).
2. **Share**.
3. Add the **`client_email`** from the JSON as **Viewer** (read-only is enough for the dashboard).
4. Do **not** share the company tracker; only the mirror.

### 1.6 Confirm access (after local env is set)

When integration is enabled later, you can verify with a one-off Python check (optional):

```python
from seller.google_sheets.client import get_sheets_client
print(get_sheets_client().ping())
```

That returns spreadsheet title and worksheet names only — no dashboard merge yet.

---

## 2. Required environment variables

Add to `.env` in the project root (copy from `.env.example`). **Never commit `.env` or the JSON key.**

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_SHEETS_ENABLED` | For live connect | `false` until you approve live load. Set `true` only when ready. |
| `GOOGLE_SHEET_MIRROR_ID` | Yes (when enabled) | Spreadsheet ID: `1uhq7vJqLSDbckeLHf2SxEjEloMHb-xLa8YimGCs9Eyk` |
| `GOOGLE_SHEETS_CREDENTIALS_PATH` | Local dev | Path to downloaded JSON, e.g. `credentials/google-service-account.json` |
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | Railway / CI | Entire Service Account JSON as **one line** in the env var (see Railway below) |
| `GOOGLE_SHEETS_SCOPES` | Optional | Default: `https://www.googleapis.com/auth/spreadsheets.readonly` |
| `GOOGLE_SHEET_PRIMARY_TAB` | Optional | Hint for merge phase: `[Raw] Shop Level - Fashion` |
| `GOOGLE_SHEETS_CONNECT_ON_STARTUP` | Optional | `false` — load sheet on dashboard open/refresh later, not at chat startup |

**Credentials rule:** provide **either** `GOOGLE_SHEETS_CREDENTIALS_PATH` **or** `GOOGLE_SHEETS_CREDENTIALS_JSON`. If both are set, **inline JSON wins** (intended for Railway).

---

## 3. Where to put the JSON locally

Recommended layout:

```text
ShopeeAI/
  credentials/
    google-service-account.json   ← your downloaded key (gitignored)
  .env                            ← paths and flags only, no key body in git
```

1. Create `credentials/` if it does not exist.
2. Move the downloaded key to `credentials/google-service-account.json`.
3. In `.env`:

```env
GOOGLE_SHEETS_ENABLED=false
GOOGLE_SHEET_MIRROR_ID=1uhq7vJqLSDbckeLHf2SxEjEloMHb-xLa8YimGCs9Eyk
GOOGLE_SHEETS_CREDENTIALS_PATH=credentials/google-service-account.json
```

`credentials/` and `*.json` under it are listed in `.gitignore` — do not commit the key.

---

## 4. How this will work on Railway

Railway has no persistent disk for arbitrary files, so use **inline JSON**:

1. Open your Service Account JSON in a text editor.
2. Minify to a **single line** (remove newlines) or paste as Railway’s multiline secret if supported.
3. In Railway → your SHP EDU service → **Variables**:
   - `GOOGLE_SHEETS_ENABLED` = `true` (only when you approve live connection)
   - `GOOGLE_SHEET_MIRROR_ID` = `1uhq7vJqLSDbckeLHf2SxEjEloMHb-xLa8YimGCs9Eyk`
   - `GOOGLE_SHEETS_CREDENTIALS_JSON` = `{ "type": "service_account", ... }` (full JSON)
   - Do **not** set `GOOGLE_SHEETS_CREDENTIALS_PATH` on Railway unless you mount a volume (not required).

4. Redeploy after changing variables.

5. Ensure the mirror sheet is still shared with the same `client_email` as in that JSON.

**Security:** treat `GOOGLE_SHEETS_CREDENTIALS_JSON` as a secret in Railway (masked variable). Rotate keys in GCP if leaked.

**Live updates:** after the merge/cache phase, the app will refresh the in-memory dataset on demand (Refresh button), not on every shop switch — Railway stays stateless; cache is per process until refresh or restart.

---

## 5. Python dependencies

Install when you are ready to test auth (dashboard still uses mock until merge phase):

```bash
pip install -r requirements.txt
```

Adds: `google-auth`, `gspread`.

---

## 6. Architecture (current vs later)

```text
Today (this task):
  .env → config.py → auth.py → client.py (optional ping only)
  seller/raw_data.py → seller/service.py → dashboard API (mock)

After your approval (later tasks):
  Refresh → client fetch all tabs → merge by Shop ID → in-memory cache
  Shop select → cache lookup → metric_resolver → recommendations
  AI Assistant: unchanged
```

Check configuration without calling Google:

```python
from seller.google_sheets.status import get_integration_status
print(get_integration_status())
```

---

## 7. Checklist before enabling live sheet

- [ ] Google Sheets API enabled in GCP project  
- [ ] Service Account created and JSON key downloaded  
- [ ] Mirror sheet shared with `client_email` (Viewer)  
- [ ] `.env` filled (or Railway variables set)  
- [ ] `GOOGLE_SHEETS_ENABLED` still `false` until merge phase approved  
- [ ] `pip install -r requirements.txt`  
- [ ] Optional: `get_sheets_client().ping()` succeeds  

---

## 8. Next phase (waiting for your approval)

1. Tab discovery on the mirror workbook  
2. Merge all tabs on Shop ID, preserve columns, in-memory cache  
3. Refresh API + dashboard UI (seller count, loading state)  
4. Replace mock `raw_data` reads with cache lookups  

Do not set `GOOGLE_SHEETS_ENABLED=true` until you confirm this setup doc and GCP sharing are complete.

---

## 9. Live connection (enabled in codebase)

After `.env` is configured:

1. Set `GOOGLE_SHEETS_ENABLED=true` and credentials path/JSON.
2. Start the app: `python app.py` or `uvicorn app:app`.
3. Open **Seller Dashboard** — data loads automatically on first visit (or click **Refresh sheet data**).
4. Optional CLI summary: `python scripts/load_mirror_sheet.py`

API:

- `GET /api/seller/status` — seller count, tabs, load state
- `POST /api/seller/refresh` — reload mirror sheet into memory
- Shop search/detail use the cache only (no Google call per shop).
