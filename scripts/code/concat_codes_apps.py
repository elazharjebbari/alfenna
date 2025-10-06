#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
concat_atelier_to_md_hardcoded.py
Parcourt /Users/elazhar/PycharmProjects/alfenna/apps/atelier,
récupère .py et .html, trie par chemin, et génère le minimum de fichiers
Markdown d'environ 1500 lignes chacun, dans /Users/elazhar/PycharmProjects/alfenna/reports/bundles
"""

from pathlib import Path
import sys

# ========= VALEURS EN DUR (spécifiques à ta machine) =========
BASE_DIR = Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\templates\\components")
OUTPUT_DIR = Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\reports\\temlpates-2components-24")
EXTENSIONS = {".py", ".html", '.yml', '.yaml'}           # ajoute ici si tu veux d'autres types
TARGET_LINES_PER_MD = 4000              # budget de lignes par fichier MD
# =============================================================

def detect_lang(ext: str) -> str:
    ext = ext.lower()
    return {
        ".py": "python",
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".js": "javascript",
        ".json": "json",
        ".md": "markdown",
        ".txt": "",
    }.get(ext, "")

def iter_source_files(base_dir: Path, exts):
    exts = {e.lower() for e in exts}
    files = []
    if not base_dir.exists():
        print(f"[ERREUR] Dossier introuvable: {base_dir}", file=sys.stderr)
        return files
    for p in base_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            files.append(p)
    files.sort(key=lambda p: p.as_posix())
    return files

def read_file_lines(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"[WARN] Lecture échouée {path}: {e}", file=sys.stderr)
        text = ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.split("\n")

def make_section(path: Path) -> tuple[str, int]:
    # Affiche le chemin relatif depuis la racine du projet
    # /Users/elazhar/PycharmProjects/alfenna/...
    # On cherche la racine en coupant après "alfenna"
    try:
        # essaie de trouver l'index de "alfenna" dans le chemin
        parts = path.parts
        if "alfenna" in parts:
            idx = parts.index("alfenna")
            rel_display = Path(*parts[idx:]).as_posix()
        else:
            rel_display = path.as_posix()
    except Exception:
        rel_display = path.as_posix()

    lines = read_file_lines(path)
    n_code = len(lines)
    lang = detect_lang(path.suffix)

    header = f"## {rel_display} ({n_code} lignes)\n\n"
    fence_start = f"```{lang}\n" if lang else "```\n"
    fence_end = "```\n\n"
    body = "\n".join(lines) + "\n"
    sep = "---\n\n"

    section = header + fence_start + body + fence_end + sep

    md_line_count = 0
    md_line_count += header.count("\n")
    md_line_count += 1              # fence start
    md_line_count += n_code         # code
    md_line_count += 2              # fence end + blank
    md_line_count += 2              # '---' + blank

    return section, md_line_count

def write_chunk(outdir: Path, index: int, content: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"atelier_bundle_{index:03d}.md"
    out.write_text(content, encoding="utf-8")
    return out

def pack_markdown(files):
    outputs = []
    buf = []
    count = 0
    idx = 1

    for p in files:
        section, sec_lines = make_section(p)

        if count == 0:
            buf.append(section)
            count += sec_lines
            continue

        if count + sec_lines <= TARGET_LINES_PER_MD:
            buf.append(section)
            count += sec_lines
        else:
            # si la section seule dépasse le budget, on la met à part
            if sec_lines > TARGET_LINES_PER_MD:
                if buf:
                    outputs.append(write_chunk(OUTPUT_DIR, idx, "".join(buf)))
                    idx += 1
                    buf, count = [], 0
                outputs.append(write_chunk(OUTPUT_DIR, idx, section))
                idx += 1
            else:
                outputs.append(write_chunk(OUTPUT_DIR, idx, "".join(buf)))
                idx += 1
                buf, count = [section], sec_lines

    if buf:
        outputs.append(write_chunk(OUTPUT_DIR, idx, "".join(buf)))

    return outputs

def main():
    files = iter_source_files(BASE_DIR, EXTENSIONS)
    if not files:
        print(f"[INFO] Aucun fichier avec extensions {sorted(EXTENSIONS)} sous {BASE_DIR}", file=sys.stderr)
        return 1

    outs = pack_markdown(files)
    print(f"[OK] {len(outs)} fichier(s) Markdown généré(s) dans: {OUTPUT_DIR}")
    print(f"[OK] Sources packées: {len(files)}")
    for p in outs:
        print(f" - {p}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
