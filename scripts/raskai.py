# apps/atelier/scripts/rask_transcription_pull.py
import os
import re
import sys
import requests
from typing import Optional

# Optionnel en dev; inerte si .env absent
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

TOKEN_URL = "https://rask-prod.auth.us-east-2.amazoncognito.com/oauth2/token"
SCOPES = "api/source api/input api/output api/limit"
PROJECTS_URL = "https://api.rask.ai/v2/projects"
TRANSCRIPTION_URL = "https://api.rask.ai/v2/projects/{project_id}/transcription"

def get_token(client_id: str, client_secret: str) -> str:
    r = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials", "scope": SCOPES},
        auth=(client_id, client_secret),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]

def normalize_name(s: str) -> str:
    # supprimer espaces, underscores ET tirets
    return re.sub(r"[-\s_]+", "", (s or "").strip().lower())

def find_project_id_by_name(token: str, name: str, page_size: int = 100) -> Optional[str]:
    if not token:
        raise RuntimeError("Token manquant pour find_project_id_by_name")
    headers = {"Authorization": f"Bearer {token}"}
    target = normalize_name(name)

    offset = 0
    while True:
        r = requests.get(
            PROJECTS_URL,
            headers=headers,
            params={"offset": offset, "limit": page_size},
            timeout=30,
        )
        r.raise_for_status()
        payload = r.json()
        projects = payload.get("projects", [])

        # match exact
        for p in projects:
            if normalize_name(p.get("name")) == target:
                return p["id"]
        # fallback: contient
        for p in projects:
            if target in normalize_name(p.get("name")):
                return p["id"]

        # pagination: sortir si on touche la fin, même si 'total' n'est pas fiable
        total = payload.get("total")
        offset += page_size
        if (total is not None and offset >= total) or len(projects) < page_size:
            break
    return None

def project_id_from_app_url(url: str) -> Optional[str]:
    m = re.search(r"/project/([0-9a-fA-F-]{36})", url or "")
    return m.group(1) if m else None

def get_transcription(token: str, project_id: str) -> dict:
    if not token:
        raise RuntimeError("Token manquant pour get_transcription")
    r = requests.get(
        TRANSCRIPTION_URL.format(project_id=project_id),
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if r.status_code == 401:
        raise RuntimeError("401 Unauthorized: vérifie RASK_TOKEN ou tes client_id/secret")
    r.raise_for_status()
    return r.json()

def _parse_script_args(args):
    # django-extensions passe une liste de strings
    params = {}
    for a in args:
        if isinstance(a, str) and "=" in a:
            k, v = a.split("=", 1)
            params[k.strip()] = v.strip()
    return params

def run(*args, **kwargs):
    # 1) needle via --script-args "needle=..."
    params = _parse_script_args(args)
    needle = params.get("needle") or os.getenv(
        "RASK_NEEDLE",
        "1_-_Introduction_et_presentation_du_materiels_KtwWjO_m8phbqY",
    )

    # 2) Auth: RASK_TOKEN direct sinon client creds -> token
    token = os.getenv("RASK_TOKEN")
    if not token:
        cid = os.getenv("RASK_CLIENT_ID")
        secret = os.getenv("RASK_CLIENT_SECRET")
        if not cid or not secret:
            print(
                "ERREUR: définis RASK_TOKEN ou RASK_CLIENT_ID/RASK_CLIENT_SECRET",
                file=sys.stderr,
            )
            return
        token = get_token(cid, secret)

    # 3) project_id depuis URL app.rask.ai ou recherche par nom
    project_id = project_id_from_app_url(needle) or find_project_id_by_name(token, needle)
    if not project_id:
        print(f"Aucun projet trouvé pour: {needle}", file=sys.stderr)
        return

    # 4) Transcription
    tr = get_transcription(token, project_id)
    segments = tr.get("segments", [])
    if not segments:
        print("Aucun segment disponible (transcription vide ou pas encore prête).", file=sys.stderr)
        return

    for seg in segments:
        start = seg.get("start")
        end = seg.get("end")
        src = (seg.get("src") or {}).get("text", "")
        dst = (seg.get("dst") or {}).get("text", "")
        line = f"[{start} -> {end}] SRC: {src}"
        if dst:
            line += f" | DST: {dst}"
        print(line)
