#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_codebook.py
Crée un "Codebook" Markdown unique et structuré pour un projet Django.

- Structure par groupes: Core, Apps (une section par app), Templates globaux, Configs, Scripts, Autres
- Front-matter YAML: stats globales, extensions, patterns exclus
- TOC global + ancres par app et par fichier
- Métadonnées par fichier: groupe/app/type/lang/loc/hash/mtime
- Code pliable via <details> pour lisibilité
- Graphe d'import Python approximatif (basé sur AST) et agrégation par app

Python >= 3.10, stdlib only.
"""

from __future__ import annotations
import os
import re
import sys
import ast
import io
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional
from datetime import datetime

# =========================
# CONFIG (variables en dur)
# =========================

CANDIDATE_ROOTS: List[Path] = [
    Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna"),
    # Path("C:/Users/Utilisateur/PycharmProjects/alfenna"),
    # Path.cwd(),
]
OUTPUT_MD: Path = Path("/mnt/c/Users/Utilisateur/PycharmProjects/alfenna/reports/PROJECT_CODEBOOK.md")

# Extensions dont le CONTENU sera inclus dans le .md
INCLUDE_EXTS: Set[str] = {".py", ".html", ".htm", ".yml", ".yaml", ".json", ".css", ".js", ".md", ".txt"}

# Globs exclus par défaut pour éviter le bruit et les artefacts lourds
EXCLUDE_GLOBS: List[str] = [
    "**/__pycache__/**",
    "**/migrations/**",
    "**/staticfiles/**",
    "**/*.min.js",
    "**/*.min.css",
    "static/**/plugins/**",
    "static/django_extensions/**",
    "static/rest_framework/**",
    "reports/**",           # désactive si tu veux inclure les pages debug HTML
]

# Taille max d'un fichier à embarquer (en octets). None = illimité.
MAX_BYTES: Optional[int] = None  # ex: 1_000_000 pour 1 MB

# Nom du projet pour affichage
PROJECT_NAME: str = "alfenna"

# =========================
# Helpers
# =========================

LANG_MAP = {
    ".py": "python",
    ".html": "html", ".htm": "html",
    ".css": "css",
    ".js": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".txt": "",
    ".yml": "yaml", ".yaml": "yaml",
}

DJ_KINDS_ORDER = [
    "apps.py", "models", "serializers", "forms", "selectors", "services", "signals",
    "permissions", "throttling", "validators", "middleware", "tasks",
    "urls", "views", "api", "admin", "management_command",
    "templates", "tests", "other",
]

@dataclass
class FileMeta:
    abs_path: Path
    rel_path: str
    ext: str
    lang: str
    lines: int
    sha256: str
    mtime_iso: str
    group: str              # 'core' | 'app:<name>' | 'templates' | 'configs' | 'scripts' | 'autres'
    app: Optional[str]      # app name if group startswith 'app:'
    kind: str               # models|views|urls|templates|tests|...|other
    module: Optional[str]   # python module path (a.b.c) if .py
    imports: List[str] = field(default_factory=list)

def pick_root() -> Path:
    for r in CANDIDATE_ROOTS:
        if r.exists():
            return r.resolve()
    return Path.cwd().resolve()

def posix(path: Path) -> str:
    return path.as_posix()

def detect_lang(ext: str) -> str:
    return LANG_MAP.get(ext.lower(), "")

def read_text_safe(p: Path) -> str:
    with open(p, "rb") as f:
        b = f.read() if MAX_BYTES is None else f.read(MAX_BYTES)
    try:
        return b.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    except Exception:
        return b.decode("latin-1", errors="replace").replace("\r\n", "\n").replace("\r", "\n")

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()

def match_any_glob(rel_posix: str, patterns: List[str]) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(rel_posix, pat) for pat in patterns)

def is_minified_name(name: str) -> bool:
    return ".min." in name

def classify_group_and_kind(root: Path, path: Path) -> Tuple[str, Optional[str], str]:
    """Retourne (group, app, kind)"""
    rel = path.relative_to(root).parts
    rel_str = "/".join(rel)

    # group
    group = "autres"
    app = None
    if rel and rel[0] == "alfenna":
        group = "core"
    elif rel and rel[0] == "apps" and len(rel) >= 2:
        app = rel[1]
        group = f"app:{app}"
    elif rel and rel[0] == "templates":
        group = "templates"
    elif rel and rel[0] == "configs":
        group = "configs"
    elif rel and rel[0] == "scripts":
        group = "scripts"

    # kind (plus fin pour Django)
    name = path.name
    stem = path.stem

    if "templates" in rel:
        kind = "templates"
    elif "management" in rel and "commands" in rel:
        kind = "management_command"
    elif "tests" in rel or name == "tests.py" or rel_str.endswith("/tests/__init__.py"):
        kind = "tests"
    elif name in {"models_base.py"} or "models" in rel[-2:-1]:
        kind = "models"
    elif name in {"views.py"} or rel_str.endswith("/views/views.py"):
        kind = "views"
    elif name in {"urls.py"}:
        kind = "urls"
    elif name in {"serializers.py"} or "serializers" in rel:
        kind = "serializers"
    elif name in {"forms.py"} or "forms" in rel:
        kind = "forms"
    elif name in {"selectors.py"}:
        kind = "selectors"
    elif name in {"services.py"} or "services" in rel:
        kind = "services"
    elif name in {"signals.py"}:
        kind = "signals"
    elif name in {"permissions.py"}:
        kind = "permissions"
    elif name in {"throttling.py"}:
        kind = "throttling"
    elif name in {"validators.py"}:
        kind = "validators"
    elif name in {"middleware.py"} or "middleware" in rel:
        kind = "middleware"
    elif name in {"tasks.py"} or "tasks" in rel:
        kind = "tasks"
    elif name in {"admin.py"}:
        kind = "admin"
    else:
        kind = "other"

    return group, app, kind

def module_from_path(root: Path, path: Path) -> Optional[str]:
    if path.suffix != ".py":
        return None
    rel = path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = Path(parts[-1]).stem
    if not parts:
        return None
    return ".".join(parts)

def resolve_relative(base_module: str, level: int, module: Optional[str]) -> Optional[str]:
    # base_module is like apps.catalog.views
    base_parts = base_module.split(".")
    if level > len(base_parts):
        return None
    base = base_parts[: len(base_parts) - level]
    if module:
        base += module.split(".")
    if not base:
        return None
    return ".".join(base)

def extract_imports_py(src: str, current_module: Optional[str]) -> List[str]:
    out: List[str] = []
    try:
        tree = ast.parse(src)
    except Exception:
        # fallback regex
        for line in src.splitlines():
            line = line.strip()
            if line.startswith("import "):
                out.append(line[7:].split(" as ")[0].strip())
            elif line.startswith("from "):
                m = re.match(r"from\s+([.\w]+)\s+import\s+", line)
                if m:
                    out.append(m.group(1))
        return out

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name:
                    out.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module
            if node.level and current_module:
                resolved = resolve_relative(current_module, node.level, mod)
                if resolved:
                    out.append(resolved)
            elif mod:
                out.append(mod)
    return out

def is_internal_module(mod: str) -> bool:
    return mod.startswith("apps.") or mod.startswith("alfenna.") or mod.startswith("manage")

def slugify_anchor(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9/_\-.]+", "-", s)
    s = s.replace("/", "-")
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "section"

# =========================
# Scan + collect metadata
# =========================

def collect_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in INCLUDE_EXTS:
            continue
        rel_posix = posix(p.relative_to(root))
        if match_any_glob(rel_posix, EXCLUDE_GLOBS):
            continue
        if is_minified_name(p.name):
            continue
        files.append(p)
    files.sort(key=lambda x: posix(x.relative_to(root)))
    return files

def build_metadata(root: Path, paths: List[Path]) -> List[FileMeta]:
    metas: List[FileMeta] = []
    for p in paths:
        rel = posix(p.relative_to(root))
        text = read_text_safe(p)
        lines = text.count("\n") + (0 if text.endswith("\n") else 1 if text else 0)
        ext = p.suffix.lower()
        lang = detect_lang(ext)
        h = sha256_text(text)
        mtime_iso = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        group, app, kind = classify_group_and_kind(root, p)
        module = module_from_path(root, p)
        imports: List[str] = extract_imports_py(text, module) if ext == ".py" else []
        metas.append(FileMeta(
            abs_path=p, rel_path=rel, ext=ext, lang=lang, lines=lines, sha256=h,
            mtime_iso=mtime_iso, group=group, app=app, kind=kind, module=module, imports=imports
        ))
    return metas

# =========================
# Stats + graph
# =========================

def summarize_ext(metas: List[FileMeta]) -> Dict[str, int]:
    d: Dict[str, int] = {}
    for m in metas:
        d[m.ext] = d.get(m.ext, 0) + m.lines
    return dict(sorted(d.items(), key=lambda kv: kv[0]))

def summarize_total_loc(metas: List[FileMeta]) -> int:
    return sum(m.lines for m in metas)

def summarize_groups(metas: List[FileMeta]) -> Dict[str, Dict[str, int]]:
    # returns { group: {"files": n, "loc": m} }
    d: Dict[str, Dict[str, int]] = {}
    for m in metas:
        g = d.setdefault(m.group, {"files": 0, "loc": 0})
        g["files"] += 1
        g["loc"] += m.lines
    return dict(sorted(d.items(), key=lambda kv: kv[0]))

def app_list(metas: List[FileMeta]) -> List[str]:
    s = sorted({m.app for m in metas if m.app})
    return [x for x in s if x]

def order_kind(kind: str) -> int:
    try:
        return DJ_KINDS_ORDER.index(kind)
    except ValueError:
        return len(DJ_KINDS_ORDER) + 1

def import_graph(metas: List[FileMeta]) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """
    Retourne:
      - graph_module: module -> set(modules internes importés)
      - graph_app: app -> set(apps importées)
    """
    graph_module: Dict[str, Set[str]] = {}
    graph_app: Dict[str, Set[str]] = {}

    # map module -> app (si module commence par apps.<app>.)
    def module_app(mod: str) -> Optional[str]:
        if mod.startswith("apps."):
            parts = mod.split(".")
            if len(parts) >= 2:
                return parts[1]
        elif mod.startswith("alfenna."):
            return "core"
        return None

    for m in metas:
        if not m.module:
            continue
        imports_internal = [imp for imp in m.imports if is_internal_module(imp)]
        if not imports_internal:
            continue
        gm = graph_module.setdefault(m.module, set())
        for imp in imports_internal:
            gm.add(imp)

        src_app = module_app(m.module)
        if src_app is None:
            continue
        ga = graph_app.setdefault(src_app, set())
        for imp in imports_internal:
            dst_app = module_app(imp)
            if dst_app and dst_app != src_app:
                ga.add(dst_app)

    return graph_module, graph_app

# =========================
# Writer (streaming)
# =========================

def write_front_matter(out: io.TextIOBase, root: Path, metas: List[FileMeta]) -> None:
    ext_stats = summarize_ext(metas)
    print("---", file=out)
    print(f"project: {PROJECT_NAME}", file=out)
    print(f"generated_at: {datetime.now().isoformat(timespec='seconds')}", file=out)
    print(f"root: {posix(root)}", file=out)
    print(f"total_files: {len(metas)}", file=out)

    total_loc = summarize_total_loc(metas)
    print(f"total_loc: {total_loc}", file=out)
    print("ext_breakdown:", file=out)
    for ext, loc in ext_stats.items():
        print(f"  {ext}: {loc}", file=out)
    print("excluded_globs:", file=out)
    for pat in EXCLUDE_GLOBS:
        print(f"  - {pat}", file=out)
    print("---\n", file=out)

def write_global_toc(out: io.TextIOBase, metas: List[FileMeta]) -> None:
    apps = app_list(metas)
    print("# Codebook du projet\n", file=out)
    print("## Sommaire", file=out)
    print("- [Résumé global](#resume-global)", file=out)
    print("- [Graphe d'import Python](#graphe-dimport-python)", file=out)
    print("- [Core](#core)", file=out)
    print("- [Apps](#apps)", file=out)
    for a in apps:
        print(f"  - [{a}](#app-{slugify_anchor(a)})", file=out)
    print("- [Templates globaux](#templates)", file=out)
    print("- [Configs](#configs)", file=out)
    print("- [Scripts](#scripts)", file=out)
    print("- [Autres](#autres)\n", file=out)

def write_global_summary(out: io.TextIOBase, metas: List[FileMeta]) -> None:
    print("## Résumé global\n", file=out)
    groups = summarize_groups(metas)
    print("| Groupe | Fichiers | Lignes |", file=out)
    print("|---|---:|---:|", file=out)
    for g, st in groups.items():
        print(f"| {g} | {st['files']} | {st['loc']} |", file=out)
    print("", file=out)

def write_import_graph(out: io.TextIOBase, metas: List[FileMeta]) -> None:
    gm, ga = import_graph(metas)
    print("## Graphe d'import Python\n", file=out)
    if not gm:
        print("_Aucun import interne détecté._\n", file=out)
        return
    print("### Par application (agrégé)\n", file=out)
    for app in sorted(ga.keys()):
        deps = ", ".join(sorted(ga[app]))
        print(f"- **{app}** → {{ {deps} }}", file=out)
    print("\n### Par module (extrait)\n", file=out)
    shown = 0
    for mod in sorted(gm.keys()):
        deps = ", ".join(sorted(gm[mod]))
        print(f"- `{mod}` → {{ {deps} }}", file=out)
        shown += 1
        if shown >= 200:  # on limite l’énumération pour rester lisible
            print("- …", file=out)
            break
    print("", file=out)

def write_group(out: io.TextIOBase, title: str, metas: List[FileMeta]) -> None:
    print(f"## {title}\n", file=out)
    # tri par kind "Django-aware", puis par chemin
    metas_sorted = sorted(metas, key=lambda m: (order_kind(m.kind), m.rel_path))
    for m in metas_sorted:
        anchor = slugify_anchor(f"file-{m.rel_path}")
        print(f'<a id="{anchor}"></a>', file=out)
        meta_line = (
            f"**{m.rel_path}** • {m.lang or m.ext[1:]} • {m.lines} lignes • "
            f"sha256: `{m.sha256[:12]}…` • mod: {m.mtime_iso}"
        )
        print(f"<details><summary>{meta_line}</summary>\n", file=out)
        code = read_text_safe(m.abs_path)
        fence = m.lang
        print(f"```{fence}".rstrip(), file=out)
        print(code, file=out, end="" if code.endswith("\n") else "\n")
        print("```\n", file=out)
        print("</details>\n", file=out)

def write_apps(out: io.TextIOBase, metas: List[FileMeta]) -> None:
    print("## Apps\n", file=out)
    apps = app_list(metas)
    for a in apps:
        print(f"### App: {a}\n", file=out)
        app_metas = [m for m in metas if m.app == a]
        # mini résumé
        files_n = len(app_metas)
        loc_n = sum(m.lines for m in app_metas)
        print(f"- **Fichiers**: {files_n}  •  **Lignes**: {loc_n}\n", file=out)
        write_group(out, f"Détails — {a}", app_metas)

def generate_codebook() -> Path:
    root = pick_root()
    root.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)

    files = collect_files(root)
    metas = build_metadata(root, files)

    with open(OUTPUT_MD, "w", encoding="utf-8", newline="\n") as out:
        write_front_matter(out, root, metas)
        write_global_toc(out, metas)
        write_global_summary(out, metas)
        write_import_graph(out, metas)

        # Core
        core_metas = [m for m in metas if m.group == "core"]
        if core_metas:
            print("## Core\n", file=out)
            write_group(out, "Core", core_metas)

        # Apps
        write_apps(out, metas)

        # Templates globaux
        tpl_metas = [m for m in metas if m.group == "templates"]
        if tpl_metas:
            print("## Templates\n", file=out)
            write_group(out, "Templates globaux", tpl_metas)

        # Configs
        cfg_metas = [m for m in metas if m.group == "configs"]
        if cfg_metas:
            print("## Configs\n", file=out)
            write_group(out, "Configs", cfg_metas)

        # Scripts
        scr_metas = [m for m in metas if m.group == "scripts"]
        if scr_metas:
            print("## Scripts\n", file=out)
            write_group(out, "Scripts", scr_metas)

        # Autres
        other_metas = [m for m in metas if m.group == "autres"]
        if other_metas:
            print("## Autres\n", file=out)
            write_group(out, "Autres", other_metas)

    return OUTPUT_MD

if __name__ == "__main__":
    out = generate_codebook()
    print(f"[OK] Codebook généré: {out}")
