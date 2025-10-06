#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
concat_multi_to_md.py
Parcourt plusieurs dossiers sources, agrège .py/.html/.y{a}ml/.css/.js/.md/.txt, trie par chemin,
puis génère des bundles Markdown avec, en tête de chaque bundle, une arborescence (TOC)
des fichiers inclus dans ce bundle.

NOUVEAU:
  - Ciblage additionnel de fichiers/dossiers via TARGET_FILES, --only, --only-file
  - Par défaut, les ciblages S'AJOUTENT au scan des BASE_DIRS
  - --exclusive pour n'inclure QUE ce qui est ciblé
  - Les entrées ciblées peuvent être: fichier, dossier, ou pattern glob
"""

import os
import sys
import glob
import argparse
from fnmatch import fnmatch
from pathlib import Path
from typing import List, Tuple, Dict, Any, Iterable

# ========= CONFIG PAR DÉFAUT =========
BASE_DIRS = [
    # Ajoute autant de dossiers que tu veux:
    Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\templates\\components\\core\\header"),
    Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\apps\\atelier\\compose\\hydrators\\header"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\apps\\content"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\apps\\flowforms"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\apps\\leads"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\templates\\components"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\templates\\screens"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\configs"),
]
OUTPUT_DIR = Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\reports\\component-header")
EXTENSIONS = {".py", ".html", ".htm", ".yml", ".yaml", ".css", ".js", ".json", ".md", ".txt"}
TARGET_LINES_PER_MD = 5000
PROJECT_ROOT_NAME = "alfenna"  # utilisé pour raccourcir l'affichage des chemins relatifs

# Ciblage supplémentaire (additionnel par défaut)
TARGET_FILES: List[os.PathLike | str] = [
    # Exemples:
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\templates\\screens_old"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\apps\\atelier\\compose\\pipeline.py"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\apps\\atelier\\compose\\load.py"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\apps\\pages\\views\\views_billing.py"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\apps\\pages\\urls.py"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\templates\\screens\\checkout.html"),
    # Path("C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\templates\\screens\\checkout.html"),
    # "C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\apps\\**\\models_base.py",
    # "C:\\Users\\Utilisateur\\PycharmProjects\\alfenna\\apps\\catalog\\scripts\\**.py",
]
EXCLUDE_PATTERNS: List[str] = [
    # Exemples:

    # "**/migrations/**",
    # "**/*.min.js",
]
# =====================================


# ----------------- Utils de base -----------------
def detect_lang(ext: str) -> str:
    return {
        ".py": "python",
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".js": "javascript",
        ".json": "json",
        ".md": "markdown",
        ".txt": "",
        ".yml": "yaml",
        ".yaml": "yaml",
    }.get(ext.lower(), "")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_file_lines(path: Path) -> List[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"[WARN] Lecture échouée {path}: {e}", file=sys.stderr)
        return []
    return normalize_newlines(text).split("\n")


def rel_display_from_project(path: Path) -> str:
    try:
        parts = path.parts
        if PROJECT_ROOT_NAME in parts:
            idx = parts.index(PROJECT_ROOT_NAME)
            return Path(*parts[idx:]).as_posix()
        return path.as_posix()
    except Exception:
        return path.as_posix()


# ----------------- Collecte de fichiers -----------------
def _scan_dir_for_ext(root: Path, exts: set[str]) -> List[Path]:
    out: List[Path] = []
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            out.append(p)
    return out


def filter_by_extensions(paths: Iterable[Path], exts: Iterable[str]) -> List[Path]:
    exts = {e.lower() for e in exts}
    return [p for p in paths if p.suffix.lower() in exts]


def filter_excludes(paths: Iterable[Path], patterns: Iterable[str] | None) -> List[Path]:
    pats: List[str] = []
    for pat in (patterns or []):
        if pat is None:
            continue
        s = os.fspath(pat).strip()
        if s:
            pats.append(s)
    if not pats:
        return list(paths)

    out: List[Path] = []
    for p in paths:
        posix = p.as_posix()
        if any(fnmatch(posix, pat) for pat in pats):
            continue
        out.append(p)
    return out


def expand_specific_files(specific_patterns: Iterable[os.PathLike | str],
                          base_dirs: List[Path],
                          exts: set[str]) -> List[Path]:
    """
    Développe chemins/patterns en fichiers.
    - Accepte fichier, dossier, glob, absolu/relatif, str/Path
    - Filtre par EXTENSIONS
    """
    found: set[Path] = set()

    def add_file(p: Path):
        try:
            if p.is_file() and p.suffix.lower() in exts:
                found.add(p.resolve())
        except Exception:
            pass

    def add_dir(d: Path):
        for child in _scan_dir_for_ext(d, exts):
            found.add(child.resolve())

    for term in (specific_patterns or []):
        if term is None:
            continue
        s = os.fspath(term).strip()
        if not s or s.startswith("#"):
            continue

        p = Path(s)
        has_glob = any(ch in s for ch in "*?[]")

        # 1) Chemin absolu
        if p.is_absolute():
            if has_glob:
                for hit in glob.glob(s, recursive=True):
                    ph = Path(hit)
                    if ph.is_dir():
                        add_dir(ph)
                    else:
                        add_file(ph)
            else:
                if p.is_dir():
                    add_dir(p)
                else:
                    add_file(p)
            continue

        # 2) Chemin relatif avec glob: tester sous chaque base puis cwd
        if has_glob:
            for base in base_dirs:
                if base.exists():
                    for hit in base.rglob(s):
                        ph = Path(hit)
                        if ph.is_dir():
                            add_dir(ph)
                        else:
                            add_file(ph)
            for hit in Path(".").rglob(s):
                ph = Path(hit)
                if ph.is_dir():
                    add_dir(ph)
                else:
                    add_file(ph)
            continue

        # 3) Chemin relatif sans glob
        resolved = False
        for base in base_dirs:
            cand = base / s
            if cand.exists():
                resolved = True
                if cand.is_dir():
                    add_dir(cand)
                else:
                    add_file(cand)
        if not resolved:
            cand = Path(s)
            if cand.exists():
                if cand.is_dir():
                    add_dir(cand)
                else:
                    add_file(cand)

    return sorted(found, key=lambda p: p.as_posix())


def collect_from_bases(base_dirs: List[Path], exts: set[str]) -> List[Path]:
    files: List[Path] = []
    any_ok = False
    for base_dir in base_dirs:
        if not base_dir.exists():
            print(f"[ERREUR] Dossier introuvable: {base_dir}", file=sys.stderr)
            continue
        any_ok = True
        files.extend(_scan_dir_for_ext(base_dir, exts))
    if not any_ok:
        print("[ERREUR] Aucun des dossiers fournis n'existe. Rien à faire.", file=sys.stderr)
    files = sorted({f.resolve() for f in files}, key=lambda p: p.as_posix())
    return files


def iter_source_files_many(
    base_dirs: List[Path],
    exts: Iterable[str],
    specific_patterns: Iterable[os.PathLike | str] | None = None,
    exclude_patterns: Iterable[str] | None = None,
    exclusive: bool = False,
) -> List[Path]:
    exts_set = {e.lower() for e in exts}

    base_files: List[Path] = [] if exclusive else collect_from_bases(base_dirs, exts_set)
    targeted_files: List[Path] = expand_specific_files(specific_patterns or [], base_dirs, exts_set)

    files_set = {*(f.resolve() for f in base_files), *(t.resolve() for t in targeted_files)}
    files = sorted(files_set, key=lambda p: p.as_posix())

    # Exclusions
    files = filter_excludes(files, exclude_patterns)

    return files


# ----------------- Construction Markdown -----------------
def make_section(path: Path) -> Tuple[str, int, int, str]:
    """Retourne (section_md, md_line_count, n_code_lines, rel_display)"""
    rel_display = rel_display_from_project(path)
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

    return section, md_line_count, n_code, rel_display


def build_tree(files_rel_with_counts: List[Tuple[str, int]]) -> str:
    """
    files_rel_with_counts: liste de tuples (rel_path_posix, n_lines)
    Retourne un bloc Markdown représentant une arborescence.
    """
    root: Dict[str, Any] = {}
    for rel, n in files_rel_with_counts:
        parts = rel.split("/")
        cur = root
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if part not in cur:
                cur[part] = {} if not last else {"__lines__": n}
            else:
                if last:
                    cur[part]["__lines__"] = n
            if not last:
                cur = cur[part]

    def render(node: Dict[str, Any], prefix: str = "") -> List[str]:
        # tri: dossiers avant fichiers, alpha
        dirs = [k for k, v in node.items() if isinstance(v, dict) and "__lines__" not in v]
        files = [k for k, v in node.items() if isinstance(v, dict) and "__lines__" in v]
        lines: List[str] = []
        for d in sorted(dirs):
            lines.append(f"{prefix}- **{d}/**")
            lines.extend(render(node[d], prefix + "  "))
        for f in sorted(files):
            n = node[f].get("__lines__", 0)
            lines.append(f"{prefix}- {f} ({n} lignes)")
        return lines

    out_lines = render(root, "")
    return "\n".join(out_lines)


def write_chunk(outdir: Path, index: int, content: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"bundle_{index:03d}.md"
    out.write_text(content, encoding="utf-8")
    return out


def write_bundle_with_toc(idx: int, sections: List[str], toc_items: List[Tuple[str, int]]) -> Path:
    """Construit le contenu final du bundle avec TOC puis écrit sur disque."""
    toc_md_list = build_tree(toc_items)
    toc_block = (
        f"# Bundle {idx:03d}\n\n"
        f"**Arborescence des fichiers inclus dans ce bundle**\n\n"
        f"{toc_md_list}\n\n"
        f"---\n\n"
    )
    content = toc_block + "".join(sections)
    return write_chunk(OUTPUT_DIR, idx, content)


def pack_markdown(files: List[Path]) -> List[Path]:
    """
    Concatène en respectant TARGET_LINES_PER_MD (approx).
    Ajoute au début de chaque bundle:
      - un titre
      - un sommaire/arborescence des fichiers inclus dans CE bundle
    """
    outputs: List[Path] = []
    buf_sections: List[str] = []
    buf_count = 0
    idx = 1
    buf_toc_items: List[Tuple[str, int]] = []

    for p in files:
        section, sec_lines, n_code, rel_display = make_section(p)

        # Si la section seule dépasse le budget, flush le buffer avant
        if sec_lines > TARGET_LINES_PER_MD:
            if buf_sections:
                outputs.append(write_bundle_with_toc(idx, buf_sections, buf_toc_items))
                idx += 1
                buf_sections, buf_toc_items, buf_count = [], [], 0
            outputs.append(write_bundle_with_toc(idx, [section], [(rel_display, n_code)]))
            idx += 1
            continue

        if buf_count + sec_lines <= TARGET_LINES_PER_MD:
            buf_sections.append(section)
            buf_toc_items.append((rel_display, n_code))
            buf_count += sec_lines
        else:
            outputs.append(write_bundle_with_toc(idx, buf_sections, buf_toc_items))
            idx += 1
            buf_sections = [section]
            buf_toc_items = [(rel_display, n_code)]
            buf_count = sec_lines

    if buf_sections:
        outputs.append(write_bundle_with_toc(idx, buf_sections, buf_toc_items))

    return outputs


def read_patterns_file(path: Path) -> List[str]:
    try:
        txt = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[ERREUR] Impossible de lire {path}: {e}", file=sys.stderr)
        return []
    out: List[str] = []
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Concat bundles avec ciblage de fichiers.")
    p.add_argument("--only", nargs="+", help="Chemins/patterns glob à inclure (s'ajoutent aux bases).")
    p.add_argument("--only-file", type=str, help="Fichier texte listant des chemins/patterns (une ligne chacun).")
    p.add_argument("--exclusive", action="store_true", help="N'inclure QUE les fichiers ciblés (ignore les bases).")
    p.add_argument("--exclude", nargs="+", help="Patterns glob à exclure (en plus de EXCLUDE_PATTERNS).")
    p.add_argument("--ext", nargs="+", help="Extensions à inclure (ex: .py .html .yml).")
    p.add_argument("--base", nargs="+", help="Bases à scanner; chemins absolus recommandés.")
    p.add_argument("--outdir", type=str, help="Répertoire de sortie.")
    p.add_argument("--target-lines", type=int, help="Lignes cibles par bundle (approx).")
    return p.parse_args()


def main() -> int:
    global OUTPUT_DIR, TARGET_LINES_PER_MD

    args = parse_args()

    base_dirs = [Path(b) for b in (args.base or [])] or BASE_DIRS
    exts = set(args.ext or []) or EXTENSIONS

    # Surcouches sur la config globale
    OUTPUT_DIR = Path(args.outdir) if args.outdir else OUTPUT_DIR
    TARGET_LINES_PER_MD = int(args.target_lines) if args.target_lines else TARGET_LINES_PER_MD

    # Construire la liste des patterns ciblés
    specific_patterns: List[os.PathLike | str] = []
    if TARGET_FILES:
        specific_patterns.extend(TARGET_FILES)
    if args.only:
        specific_patterns.extend(args.only)
    if args.only_file:
        specific_patterns.extend(read_patterns_file(Path(args.only_file)))

    exclude_patterns: List[str] = []
    if EXCLUDE_PATTERNS:
        exclude_patterns.extend(EXCLUDE_PATTERNS)
    if args.exclude:
        exclude_patterns.extend(args.exclude)

    files = iter_source_files_many(
        base_dirs=base_dirs,
        exts=exts,
        specific_patterns=specific_patterns or None,
        exclude_patterns=exclude_patterns or None,
        exclusive=bool(args.exclusive),
    )

    if not files:
        print(
            f"[INFO] Aucun fichier trouvé. Extensions: {sorted(exts)} | "
            f"Bases: {', '.join(str(p) for p in base_dirs)} | "
            f"only={specific_patterns or '—'} | exclusive={args.exclusive}",
            file=sys.stderr,
        )
        return 1

    outs = pack_markdown(files)
    print(f"[OK] {len(outs)} fichier(s) Markdown généré(s) dans: {OUTPUT_DIR}")
    print(f"[OK] Sources packées: {len(files)}")
    for p in outs:
        print(f" - {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
