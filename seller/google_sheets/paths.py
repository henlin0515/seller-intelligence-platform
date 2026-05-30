"""
Project-root path resolution for Google Sheets credentials and assets.
Project root = directory containing app.py.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("seller.google_sheets")

# Known filenames under credentials/ (checked if env path is missing)
CREDENTIALS_FALLBACK_RELATIVE: tuple[str, ...] = (
    "credentials/service-account.json",
    "credentials/service-account.json.json",
    "credentials/service-account.json.txt",
    "credentials/google-service-account.json",
)


def get_project_root() -> Path:
    """Return SHP EDU project root (folder that contains app.py)."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "app.py").is_file():
            return parent
    return here.parents[2]


def _credentials_dir(root: Path) -> Path:
    return root / "credentials"


def _discover_credentials_file(root: Path) -> Path | None:
    """Find service account JSON in credentials/ when env path does not exist."""
    cred_dir = _credentials_dir(root)
    if not cred_dir.is_dir():
        return None

    for rel in CREDENTIALS_FALLBACK_RELATIVE:
        candidate = (root / rel).resolve()
        if candidate.is_file():
            return candidate

    preferred_names = (
        "service-account.json",
        "service-account.json.json",
        "service-account.json.txt",
        "google-service-account.json",
    )
    for name in preferred_names:
        candidate = cred_dir / name
        if candidate.is_file():
            return candidate.resolve()

    # Last resort: sole *service*account* key file in credentials/
    matches = sorted(
        p.resolve()
        for p in cred_dir.iterdir()
        if p.is_file()
        and "service" in p.name.lower()
        and "account" in p.name.lower()
        and p.suffix.lower() in (".json", ".txt", "")
    )
    if len(matches) == 1:
        return matches[0]
    if matches:
        return matches[0]

    return None


def resolve_credentials_path(credentials_path: str) -> Path:
    """
    Resolve GOOGLE_SHEETS_CREDENTIALS_PATH relative to project root.
    If missing, auto-discover credentials/service-account*.json in project root.
    """
    root = get_project_root()
    raw = credentials_path.strip()
    primary: Path | None = None

    if raw:
        path = Path(raw)
        primary = path.resolve() if path.is_absolute() else (root / path).resolve()

    if primary and primary.is_file():
        logger.info(
            "Resolved GOOGLE_SHEETS_CREDENTIALS_PATH: env=%r -> %s (project_root=%s)",
            raw,
            primary,
            root,
        )
        return primary

    discovered = _discover_credentials_file(root)
    if discovered:
        logger.warning(
            "GOOGLE_SHEETS_CREDENTIALS_PATH env file not found (%s); using discovered credentials: %s",
            primary,
            discovered,
        )
        logger.info(
            "Resolved GOOGLE_SHEETS_CREDENTIALS_PATH: env=%r -> %s (project_root=%s)",
            raw,
            discovered,
            root,
        )
        return discovered

    fallback = primary or (root / "credentials" / "service-account.json").resolve()
    logger.error(
        "Credentials file not found. env=%r resolved=%s project_root=%s credentials_dir=%s",
        raw,
        fallback,
        root,
        _credentials_dir(root),
    )
    return fallback
