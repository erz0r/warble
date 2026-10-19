"""a tuning project: a score text file plus its edit history.

every saved edit is a version under `.warble/<file name>/versions/`; `state.json` holds the current
version, the redo stack, named snapshots and a log of which op produced each version. undo and redo
rewrite the project file from a stored version, so the file on disk is always the current state and
stays diff-friendly.
"""

import datetime
import difflib
import json
import os

from ..errors import WarbleError
from ..score import load, parse_text


class Project:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        if not os.path.isfile(self.path):
            raise WarbleError("project_missing", f"no project file at {path}", hint="create one with `warble export <score> -o project.txt` or `warble new`")
        base = os.path.dirname(self.path)
        self.hist = os.path.join(base, ".warble", os.path.basename(self.path))
        os.makedirs(os.path.join(self.hist, "versions"), exist_ok=True)
        self.state_path = os.path.join(self.hist, "state.json")
        if os.path.isfile(self.state_path):
            with open(self.state_path, encoding="utf-8") as f:
                self.state = json.load(f)
        else:
            self.state = {"current": 0, "head": 0, "snapshots": {}, "log": [{"version": 0, "op": "initial", "time": _now()}]}
            self._write_version(0, self.text())
            self._save_state()
        # an outside edit to the file becomes a version of its own
        if self.text() != self._read_version(self.state["current"]):
            self._commit(self.text(), "external edit", {})

    # ---- io ------------------------------------------------------------------------------

    def text(self):
        with open(self.path, encoding="utf-8-sig") as f:
            return f.read()

    def score(self):
        if self.path.endswith(".txt") or self.path.endswith(".score"):
            return parse_text(self.text(), base_dir=os.path.dirname(self.path), source=os.path.basename(self.path))
        return load(self.path)

    def _vpath(self, n):
        return os.path.join(self.hist, "versions", f"{n:05d}.txt")

    def _write_version(self, n, text):
        with open(self._vpath(n), "w", encoding="utf-8") as f:
            f.write(text)

    def _read_version(self, n):
        with open(self._vpath(n), encoding="utf-8") as f:
            return f.read()

    def _save_state(self):
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=1)

    def _commit(self, text, op, args):
        n = self.state["current"] + 1
        self._write_version(n, text)
        self.state["current"] = n
        self.state["head"] = n  # a new edit drops the redo branch
        self.state["log"] = [e for e in self.state["log"] if e["version"] < n] + [{"version": n, "op": op, "args": args, "time": _now()}]
        self._save_state()
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)
        return n

    # ---- api -----------------------------------------------------------------------------

    def save_score(self, score, op, args=None):
        text = score.to_text()
        if text == self.text():
            return {"version": self.state["current"], "changed": False}
        n = self._commit(text, op, args or {})
        return {"version": n, "changed": True}

    def undo(self, steps=1):
        cur = self.state["current"]
        target = max(0, cur - steps)
        return self._goto(target, "undo")

    def redo(self, steps=1):
        target = min(self.state["head"], self.state["current"] + steps)
        return self._goto(target, "redo")

    def _goto(self, n, why):
        text = self._read_version(n)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)
        self.state["current"] = n
        self._save_state()
        return {"version": n, "head": self.state["head"], "action": why, "op_at_version": self._op(n)}

    def _op(self, n):
        for e in self.state["log"]:
            if e["version"] == n:
                return e["op"]
        return None

    def snapshot(self, name):
        self.state["snapshots"][name] = self.state["current"]
        self._save_state()
        return {"snapshot": name, "version": self.state["current"]}

    def restore(self, name):
        if name not in self.state["snapshots"]:
            raise WarbleError("snapshot_missing", f"no snapshot '{name}'", hint=f"snapshots: {sorted(self.state['snapshots'])}")
        text = self._read_version(self.state["snapshots"][name])
        n = self._commit(text, f"restore {name}", {})
        return {"version": n, "restored": name}

    def resolve(self, ref):
        """a version number, a snapshot name, 'current', or 'prev'."""
        if ref in (None, "current"):
            return self.state["current"]
        if ref == "prev":
            return max(0, self.state["current"] - 1)
        if ref in self.state["snapshots"]:
            return self.state["snapshots"][ref]
        try:
            n = int(ref)
        except ValueError:
            raise WarbleError("version_unknown", f"no version or snapshot '{ref}'")
        if not os.path.isfile(self._vpath(n)):
            raise WarbleError("version_unknown", f"version {n} does not exist")
        return n

    def diff(self, a="prev", b="current"):
        va, vb = self.resolve(a), self.resolve(b)
        ta, tb = self._read_version(va), self._read_version(vb)
        text = list(difflib.unified_diff(ta.splitlines(), tb.splitlines(), f"v{va}", f"v{vb}", lineterm="", n=0))
        sa = parse_text(ta, base_dir=os.path.dirname(self.path))
        sb = parse_text(tb, base_dir=os.path.dirname(self.path))
        notes = []
        for tr_a, tr_b in zip(sa.tracks, sb.tracks):
            for i, (na, nb) in enumerate(zip(tr_a.notes, tr_b.notes), start=1):
                changes = {}
                for k in ("lyric", "tone", "position", "duration"):
                    if getattr(na, k) != getattr(nb, k):
                        changes[k] = [getattr(na, k), getattr(nb, k)]
                for k in sorted(set(na.controls) | set(nb.controls)):
                    if na.controls.get(k) != nb.controls.get(k):
                        changes[k] = [na.controls.get(k), nb.controls.get(k)]
                if changes:
                    notes.append({"track": tr_b.name, "note": i, "lyric": nb.lyric, "changes": changes})
            if len(tr_a.notes) != len(tr_b.notes):
                notes.append({"track": tr_b.name, "note_count": [len(tr_a.notes), len(tr_b.notes)]})
        return {"from": va, "to": vb, "notes": notes, "text_diff": text}

    def history(self):
        return {"current": self.state["current"], "head": self.state["head"], "snapshots": self.state["snapshots"], "log": self.state["log"]}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")
