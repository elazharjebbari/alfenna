"""
Django-extensions runscript
Génère un refresh token Google Ads en mode loopback (auto) ou manuel.

Usage:
  python manage.py runscript apps.adsbridge.scripts.get_refresh_token
  python manage.py runscript apps.adsbridge.scripts.get_refresh_token --script-args "mode=auto port=0 dotenv=.env update_env=1"
  python manage.py runscript apps.adsbridge.scripts.get_refresh_token --script-args "mode=manual port=8085 dotenv=.env"

Args (key=value) :
  mode        : auto | manual   (def: auto)
  port        : 0 = port libre  (def: 0)  ex: 8085 si tu veux fixer
  dotenv      : chemin du .env  (def: .env)
  update_env  : 1 = écris GADS_REFRESH_TOKEN dans le .env (def: 0)
  open_browser: 1/0 (def: 1 en auto ; ignoré en manuel)

Prérequis:
  - .env contient GADS_CLIENT_ID et GADS_CLIENT_SECRET
  - Client OAuth = "Application de bureau"
  - Consent screen = Externe + ton email dans la liste des testeurs
  - API "Google Ads API" activée dans GCP
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from google_auth_oauthlib.flow import InstalledAppFlow

# Chargement .env
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def _parse_args(raw_args):
    """Parse --script-args 'k=v k=v' en dict."""
    out = {}
    for tok in raw_args:
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _load_env(dotenv_path):
    if load_dotenv is None:
        print("[WARN] python-dotenv non installé. Lecture directe des variables d'environnement.")
        return
    p = Path(dotenv_path).expanduser()
    if p.exists():
        load_dotenv(dotenv_path=str(p))
        print(f"[INFO] .env chargé : {p}")
    else:
        print(f"[WARN] Fichier .env introuvable : {p} (on continue avec l'environnement actuel)")


def _update_env_file(dotenv_path, key, value):
    p = Path(dotenv_path).expanduser()
    if not p.exists():
        print(f"[WARN] .env absent, création : {p}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"{key}={value}\n", encoding="utf-8")
        return
    lines = p.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[INFO] Mis à jour dans {p}: {key}=***")


def run(*script_args):
    # ---------- 1) Lecture des args ----------
    args = _parse_args(script_args)
    mode = args.get("mode", "auto").lower()          # auto | manual
    port = int(args.get("port", "0"))                # 0 = port libre
    dotenv_path = args.get("dotenv", ".env")
    update_env = args.get("update_env", "0") == "1"
    open_browser = args.get("open_browser", "1") == "1"

    # ---------- 2) Charge .env ----------
    _load_env(dotenv_path)

    client_id = os.getenv("GADS_CLIENT_ID")
    client_secret = os.getenv("GADS_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("[ERR ] GADS_CLIENT_ID ou GADS_CLIENT_SECRET manquant(s) dans l'environnement/.env")
        sys.exit(2)

    # ---------- 3) Flow OAuth (Desktop/Loopback) ----------
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                # Desktop app loopback
                "redirect_uris": ["http://localhost", "http://127.0.0.1"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/adwords"],
    )

    # Par défaut, le flow choisira un redirect loopback; si on veut fixer le port en manuel:
    if mode == "manual":
        flow.redirect_uri = f"http://localhost:{port}" if port else "http://localhost"

    print(f"[INFO] Mode: {mode} | Port: {port} | Update .env: {update_env}")

    # ---------- 4) AUTO : run_local_server ----------
    if mode == "auto":
        try:
            print("[INFO] Ouverture du navigateur (loopback)…")
            creds = flow.run_local_server(port=port, open_browser=open_browser, prompt="consent")
            rt = getattr(creds, "refresh_token", None)
            if not rt:
                print("[ERR ] Aucun refresh_token retourné. Réessaie avec prompt='consent' et email testeur.")
                sys.exit(2)
            print(f"[OK  ] REFRESH TOKEN: {rt}")
            if update_env:
                _update_env_file(dotenv_path, "GADS_REFRESH_TOKEN", rt)
            return
        except Exception as e:
            print(f"[WARN] run_local_server a échoué ({e}). On passe en MANUAL fallback…")
            mode = "manual"

    # ---------- 5) MANUAL : URL d'autorisation + URL complète de redirection ----------
    # Ici, on affiche l'URL, tu l’ouvres dans n’importe quel navigateur (même une autre machine),
    # puis tu colles l’URL **complète** après redirection (http://localhost:PORT/?code=...&scope=...)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    print("\n[STEP] Ouvre cette URL dans un navigateur, autorise l'accès,")
    print("      puis COLLE ICI L'URL COMPLÈTE après redirection (http://localhost:PORT/?code=...):\n")
    print(auth_url, "\n")
    full_redirect = input("URL complète de redirection: ").strip()

    # Sanity: extraire 'code' pour vérifier qu'on a bien une URL complète
    try:
        q = parse_qs(urlparse(full_redirect).query)
        assert "code" in q and q["code"][0], "URL incomplète: paramètre 'code' absent."
    except Exception as e:
        print(f"[ERR ] {e}\nAstuce: copie/colle TOUTE l'URL après consentement (elle commence par http://localhost:PORT/...)")
        sys.exit(2)

    # Échange du code contre les tokens
    flow.fetch_token(authorization_response=full_redirect)
    creds = flow.credentials
    rt = getattr(creds, "refresh_token", None)
    if not rt:
        print("[ERR ] Aucun refresh_token dans la réponse. Assure-toi d'avoir 'access_type=offline' et 'prompt=consent'.")
        sys.exit(2)

    print(f"\n[OK  ] REFRESH TOKEN: {rt}")
    if update_env:
        _update_env_file(dotenv_path, "GADS_REFRESH_TOKEN", rt)
        print(f"[OK  ] Ajouté à {dotenv_path} sous GADS_REFRESH_TOKEN")
