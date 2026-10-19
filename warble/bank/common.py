"""bank-type-independent pieces: character files, readmes, folder trees, type detection."""

import os
import re

import yaml

from ..textenc import read_text

try:
    _Loader = yaml.CSafeLoader
except AttributeError:  # pragma: no cover
    _Loader = yaml.SafeLoader

README_PAT = re.compile(r"(read[ _-]?me|^\$read$|license|licence|terms|kiyaku|利用規約|規約|はじめに|お読みください|説明書|how to use|使い方)", re.I)
TEXT_EXT = {".txt", ".md", ".pdf", ".html", ".htm", ".rtf", ""}


def load_yaml(path):
    with open(path, "rb") as f:
        data = f.read()
    text = data.decode("utf-8-sig", errors="replace")
    return yaml.load(text, Loader=_Loader)


def camel_to_snake(name):
    """openutau reads yaml with yamldotnet's underscored naming, so camelCase c# fields
    appear as snake_case keys. accept both spellings."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def load_character_yaml(root):
    path, _ = find_file_ci(root, "character.yaml")
    if not path:
        return None, None
    try:
        data = load_yaml(path) or {}
    except Exception as e:  # noqa: BLE001
        return path, {"_error": f"cannot parse character.yaml: {e}"}
    if not isinstance(data, dict):
        return path, {"_error": "character.yaml is not a mapping"}
    return path, {camel_to_snake(k): v for k, v in data.items()}


def find_file_ci(root, name):
    """find a file by name ignoring case. returns (path, exact_case) or (None, None).
    banks made on windows often ship Character.txt, which only works on case-insensitive disks."""
    try:
        entries = os.listdir(root)
    except OSError:
        return None, None
    if name in entries and os.path.isfile(os.path.join(root, name)):
        return os.path.join(root, name), True
    for e in entries:
        if e.lower() == name.lower() and os.path.isfile(os.path.join(root, e)):
            return os.path.join(root, e), False
    return None, None


def parse_character_txt(root, declared_encoding=None):
    """parse character.txt the way openutau does: key=value, key:value or key：value lines."""
    path, exact = find_file_ci(root, "character.txt")
    if not path:
        return None
    text, enc, how = read_text(path, declared_encoding)
    info = {"path": path, "encoding": enc, "encoding_how": how}
    if not exact:
        info["wrong_case"] = os.path.basename(path)
    other = []
    for raw in text.splitlines():
        line = raw.strip()
        parts = None
        for sep in ("=", ":", "："):
            if sep in line:
                parts = line.split(sep, 1)
                break
        if parts:
            key, val = parts[0].strip().lower(), parts[1].strip()
            if key == "name" or (key == "名前" and "name" not in info):
                info["name"] = val
            elif key == "image":
                info["image"] = val
            elif key in ("author", "created by"):
                info["author"] = val
            elif key.startswith("voice") or key == "cv":
                info["voice"] = val
            elif key == "sample":
                info["sample"] = val
            elif key == "web":
                info["web"] = val
            elif key == "version":
                info["version"] = val
            else:
                other.append(line)
        elif line:
            other.append(line)
    if other:
        info["other"] = other[:20]
    return info


def find_readmes(root, max_depth=2):
    """readme / license / terms files near the bank root, for the agent to read before use."""
    found = []
    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.count(os.sep) - root_depth
        in_terms_dir = dirpath != root and README_PAT.search(os.path.basename(dirpath))
        if depth >= max_depth:
            dirnames[:] = []
        for fn in filenames:
            stem, ext = os.path.splitext(fn)
            if ext.lower() in TEXT_EXT and (in_terms_dir or README_PAT.search(stem) or README_PAT.search(fn)):
                found.append(os.path.join(dirpath, fn))
    found.sort(key=lambda p: (p.count(os.sep), p))
    return found


def tree(root, max_depth=3, max_files_per_dir=12):
    """compact folder tree: directories with file counts, extension histograms and a few names."""
    out = []
    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        depth = dirpath.count(os.sep) - root_depth
        rel = os.path.relpath(dirpath, root)
        files = sorted(f for f in filenames if not f.startswith("."))
        exts = {}
        for f in files:
            e = os.path.splitext(f)[1].lower() or "(none)"
            exts[e] = exts.get(e, 0) + 1
        entry = {"dir": rel, "files": len(files), "by_ext": exts}
        notable = [f for f in files if not f.lower().endswith((".wav", ".frq", ".llsm", ".mrq", ".dio", ".pmk"))]
        if notable:
            entry["notable"] = notable[:max_files_per_dir]
            if len(notable) > max_files_per_dir:
                entry["notable_more"] = len(notable) - max_files_per_dir
        out.append(entry)
        if depth >= max_depth:
            if dirnames:
                entry["subdirs_not_shown"] = len(dirnames)
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
    return out


def has_oto_below(root, max_depth=3):
    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        if "oto.ini" in filenames:
            return os.path.join(dirpath, "oto.ini")
        if dirpath.count(os.sep) - root_depth >= max_depth:
            dirnames[:] = []
    return None


def detect(root):
    """decide what kind of bank a folder is. returns (type, evidence) where type is
    'diffsinger', 'utau' or 'unsupported'."""
    root = os.path.abspath(root)
    evidence = []
    if not os.path.isdir(root):
        return "missing", [f"{root} is not a directory"]
    _, cy = load_character_yaml(root)
    singer_type = (cy or {}).get("singer_type")
    if singer_type:
        evidence.append(f"character.yaml singer_type: {singer_type}")
        st = str(singer_type).lower()
        if st == "diffsinger":
            return "diffsinger", evidence
        if st in ("utau", "classic"):
            return "utau", evidence
        return "unsupported", evidence + [f"singer_type '{singer_type}' is not diffsinger or utau"]
    if os.path.isfile(os.path.join(root, "dsconfig.yaml")):
        return "diffsinger", evidence + ["dsconfig.yaml at root"]
    if os.path.isfile(os.path.join(root, "enuconfig.yaml")):
        return "unsupported", evidence + ["enuconfig.yaml at root: this is an enunu/nnsvs bank"]
    oto = has_oto_below(root)
    if oto:
        evidence.append(f"oto.ini at {os.path.relpath(oto, root)}")
        if os.path.isfile(os.path.join(root, "character.txt")):
            evidence.append("character.txt at root")
        return "utau", evidence
    seen = sorted(os.listdir(root))[:30]
    return "unsupported", evidence + [f"no dsconfig.yaml, character.yaml singer_type or oto.ini; top-level entries: {seen}"]


BANK_MARKERS = ("character.txt", "character.yaml", "dsconfig.yaml")


def has_marker(folder):
    return any(find_file_ci(folder, m)[0] for m in BANK_MARKERS)


def config_files(root):
    """yaml/ini/map files at the bank root besides character.* and oto.ini; these are usually
    phonemizer data (presamp.ini, arpasing.yaml, en-cPv.yaml, dsdict*.yaml)."""
    out = []
    for fn in sorted(os.listdir(root)):
        low = fn.lower()
        if low in ("character.yaml", "character.txt", "oto.ini", "dsconfig.yaml", "desktop.ini") or low.startswith("tmp-"):
            continue
        if low.endswith((".yaml", ".yml", ".ini", ".map", ".json")):
            out.append(fn)
    return out


def scan(base, max_depth=4):
    """find bank roots under a folder. a bank root is the shallowest folder holding one of the
    marker files (or an oto.ini with no marker above it); we don't descend into a bank root."""
    base = os.path.abspath(base)
    roots = []
    base_depth = base.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        lower = {f.lower() for f in filenames}
        if dirpath != base and (any(m in lower for m in BANK_MARKERS) or "oto.ini" in lower):
            roots.append(dirpath)
            dirnames[:] = []
            continue
        if dirpath.count(os.sep) - base_depth >= max_depth:
            dirnames[:] = []
    return roots
