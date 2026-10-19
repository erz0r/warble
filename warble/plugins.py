"""host installed vst3 / audio unit effects (via spotify's pedalboard) inside the mix.

score syntax, on a track's `fx` line or the `master` line:
    fx chain=OTT(depth=30;time=40)>ShaperBox3()
    master chain=OTT(depth=15)
plugins run left to right. names match installed plugins loosely (case, spaces and punctuation are
ignored; 'ott' finds OTT.vst3). parameters use the plugin's own names as `warble plugins info <name>`
lists them; `preset=<path>` loads a .vstpreset / .aupreset first. instruments are refused.

search folders: the standard vst3 and component folders for the system and the user, plus
$WARBLE_PLUGINS (os.pathsep separated).
"""

import os
import re
import sys

import numpy as np

from .errors import WarbleError

_CACHE = {}


def plugin_dirs():
    home = os.path.expanduser("~")
    dirs = [d for d in os.environ.get("WARBLE_PLUGINS", "").split(os.pathsep) if d]
    if sys.platform == "darwin":
        dirs += ["/Library/Audio/Plug-Ins/VST3", f"{home}/Library/Audio/Plug-Ins/VST3",
                 "/Library/Audio/Plug-Ins/Components", f"{home}/Library/Audio/Plug-Ins/Components"]
    elif sys.platform.startswith("linux"):
        dirs += [f"{home}/.vst3", "/usr/lib/vst3", "/usr/local/lib/vst3"]
    else:
        dirs += [r"C:\Program Files\Common Files\VST3"]
    return [d for d in dirs if os.path.isdir(d)]


def _key(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def scan():
    """installed plugin bundles: [{name, path, format}] (vst3 preferred over au for the same name)."""
    found = {}
    for d in plugin_dirs():
        for root, dirs, _ in os.walk(d):
            for sub in list(dirs):
                low = sub.lower()
                if low.endswith((".vst3", ".component")):
                    fmt = "vst3" if low.endswith(".vst3") else "au"
                    name = os.path.splitext(sub)[0]
                    entry = {"name": name, "path": os.path.join(root, sub), "format": fmt}
                    k = _key(name)
                    if k not in found or (found[k]["format"] == "au" and fmt == "vst3"):
                        found[k] = entry
                    dirs.remove(sub)  # don't walk inside bundles
    return sorted(found.values(), key=lambda e: e["name"].lower())


def find(name):
    plugs = scan()
    k = _key(name)
    exact = [p for p in plugs if _key(p["name"]) == k]
    if exact:
        return exact[0]
    part = [p for p in plugs if k and k in _key(p["name"])]
    if len(part) == 1:
        return part[0]
    raise WarbleError("plugin_missing" if not part else "plugin_ambiguous", f"no single installed plugin matches '{name}'",
                      hint="`warble plugins` lists what is installed", candidates=[p["name"] for p in (part or plugs)][:30])


def load(name):
    try:
        import pedalboard
    except ImportError:
        raise WarbleError("pedalboard_missing", "plugin hosting needs pedalboard", hint="pip install pedalboard")
    p = find(name)
    if p["path"] not in _CACHE:
        try:
            plug = pedalboard.load_plugin(p["path"])
        except Exception as e:  # noqa: BLE001
            raise WarbleError("plugin_load_failed", f"could not load {p['name']} ({p['format']}): {e}", path=p["path"])
        if getattr(plug, "is_instrument", False):
            raise WarbleError("plugin_is_instrument", f"{p['name']} is an instrument, not an effect")
        _CACHE[p["path"]] = plug
    return _CACHE[p["path"]], p


def info(name):
    plug, p = load(name)
    params = {}
    for k, v in plug.parameters.items():
        rng = getattr(v, "range", None)
        params[k] = {"value": _jsonable(getattr(plug, k, None)), "range": [_jsonable(x) for x in rng] if rng else None}
        vals = getattr(v, "valid_values", None)
        if vals and len(vals) <= 24:
            params[k]["choices"] = [str(x) for x in vals]
    return {**p, "parameters": params}


def _jsonable(x):
    if isinstance(x, float) and not np.isfinite(x):
        return str(x)
    return x if isinstance(x, (int, float, str, bool)) or x is None else str(x)


def parse_chain(spec):
    """'OTT(depth=30;time=40)>Shaper Box 3()' -> [(name, {param: value})]."""
    out = []
    for item in str(spec).split(">"):
        item = item.strip()
        if not item:
            continue
        m = re.fullmatch(r"([^()]+?)\s*(?:\((.*)\))?", item)
        if not m:
            raise WarbleError("bad_chain", f"cannot read plugin '{item}'", hint="Name(param=value;param=value)>Next()")
        params = {}
        for kv in (m.group(2) or "").split(";"):
            if not kv.strip():
                continue
            if "=" not in kv:
                raise WarbleError("bad_chain", f"plugin parameter '{kv}' needs '='")
            k, v = kv.split("=", 1)
            params[k.strip()] = v.strip()
        out.append((m.group(1).strip(), params))
    return out


def _coerce(v):
    lv = str(v).lower()
    if lv in ("true", "on", "yes"):
        return True
    if lv in ("false", "off", "no"):
        return False
    try:
        return float(v)
    except ValueError:
        return v


def run_chain(audio, sr, spec):
    """audio: [n] or [n, 2] float. returns [n, 2]."""
    x = np.asarray(audio, np.float32)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    buf = np.ascontiguousarray(x.T)
    for name, params in parse_chain(spec):
        plug, p = load(name)
        plug.reset()
        preset = params.pop("preset", None)
        if preset:
            try:
                plug.load_preset(os.path.expanduser(preset))
            except Exception as e:  # noqa: BLE001
                raise WarbleError("plugin_preset_failed", f"{p['name']}: cannot load preset {preset}: {e}")
        for k, v in params.items():
            if k not in plug.parameters:
                raise WarbleError("plugin_param_unknown", f"{p['name']} has no parameter '{k}'",
                                  hint=f"parameters: {sorted(plug.parameters)}")
            try:
                setattr(plug, k, _coerce(v))
            except Exception as e:  # noqa: BLE001
                raise WarbleError("plugin_param_bad", f"{p['name']}.{k} = {v}: {e}", range=str(getattr(plug.parameters[k], "range", "")))
        # a tail so reverbs/delays inside the plugin ring out
        out = plug.process(buf, sr, reset=True)
        if out.ndim == 1:
            out = np.stack([out, out])
        buf = np.ascontiguousarray(out[:2] if out.shape[0] >= 2 else np.vstack([out, out]))
    return buf.T.astype(np.float64)
