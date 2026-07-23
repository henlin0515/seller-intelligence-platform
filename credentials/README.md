# Credentials (local only)

Place your Google Service Account JSON here as:

`service-account.json`

(Must match `GOOGLE_SHEETS_CREDENTIALS_PATH` in `.env`.)

## FastMoss session cookie

Export (preferred — log in once in the opened browser):

```text
py -3 scripts/export_fastmoss_cookie.py --login
```

Then set in `.env` (local) or Railway Variables:

```text
FASTMOSS_COOKIE_FILE=credentials/fastmoss_cookie.txt
# or paste the file contents as:
# FASTMOSS_COOKIE=...
```

This folder is gitignored. See `GOOGLE_SHEETS_SETUP.md` in the project root.
