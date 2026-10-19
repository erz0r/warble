"""onnxruntime sessions: lazy, cached in-process, fed by graph signature, with an on-disk tensor cache.

`run()` is the only way models get called. it reads the session's real inputs, casts each feed to
the graph's dtype and rank, drops feeds the graph doesn't take (reporting them), and raises a
specific error naming any input the graph needs that nobody built. that's what keeps odd or old
banks working instead of crashing deep inside onnxruntime.
"""

import hashlib
import os
import sys
import time

import numpy as np

from .errors import WarbleError

_SESSIONS = {}
_DTYPES = {
    "tensor(float)": np.float32,
    "tensor(float16)": np.float16,
    "tensor(double)": np.float64,
    "tensor(int64)": np.int64,
    "tensor(int32)": np.int32,
    "tensor(bool)": np.bool_,
}
PROVIDER = os.environ.get("WARBLE_PROVIDER", "cpu")
CACHE_DIR = os.environ.get("WARBLE_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "warble", "tensors"))
STATS = {"session_loads": [], "runs": [], "cache_hits": 0}
CACHE_ENABLED = os.environ.get("WARBLE_NO_CACHE") is None


def set_provider(name):
    global PROVIDER
    PROVIDER = name


def _providers():
    import onnxruntime as ort

    avail = ort.get_available_providers()
    if PROVIDER == "coreml" and "CoreMLExecutionProvider" in avail:
        return ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    if PROVIDER == "cuda" and "CUDAExecutionProvider" in avail:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if PROVIDER not in ("cpu", None):
        print(f"warble: provider '{PROVIDER}' unavailable ({avail}); using cpu", file=sys.stderr)
    return ["CPUExecutionProvider"]


def session(path):
    import onnxruntime as ort

    key = (os.path.abspath(path), PROVIDER)
    st = os.stat(path)
    cached = _SESSIONS.get(key)
    if cached and cached[1] == (st.st_mtime, st.st_size):
        return cached[0]
    t0 = time.time()
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    sess = ort.InferenceSession(path, sess_options=opts, providers=_providers())
    STATS["session_loads"].append({"model": path, "seconds": round(time.time() - t0, 3)})
    _SESSIONS[key] = (sess, (st.st_mtime, st.st_size))
    return sess


def _hash_feeds(path, feeds, extra=""):
    st = os.stat(path)
    h = hashlib.sha256(f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime}|{extra}".encode())
    for k in sorted(feeds):
        a = np.ascontiguousarray(feeds[k])
        h.update(k.encode())
        h.update(str(a.dtype).encode())
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()[:32]


def run(path, feeds, role, cache=True, seed=None, outputs=None):
    """run a model. returns {output_name: array}. role names the model in errors ('acoustic', ...)."""
    sess = session(path)
    graph_inputs = {i.name: i for i in sess.get_inputs()}
    missing = [n for n in graph_inputs if n not in feeds]
    if missing:
        raise WarbleError(
            "model_input_missing",
            f"the {role} model at {path} needs inputs {missing} that the pipeline did not build",
            hint="the bank's dsconfig flags probably disagree with the graph; run `warble probe --check` on the bank",
            graph_inputs=sorted(graph_inputs), fed=sorted(feeds),
        )
    dropped = sorted(n for n in feeds if n not in graph_inputs)
    ready = {}
    for name, meta in graph_inputs.items():
        arr = np.asarray(feeds[name])
        dt = _DTYPES.get(meta.type)
        if dt is not None and arr.dtype != dt:
            arr = arr.astype(dt)
        rank = len(meta.shape)
        if arr.ndim != rank:
            if arr.size == 1 and rank in (0, 1):
                arr = arr.reshape(() if rank == 0 else (1,))
            else:
                raise WarbleError("model_input_rank", f"{role} input '{name}' has shape {arr.shape} but the graph wants rank {rank} {meta.shape}")
        ready[name] = arr
    key = None
    cache = cache and CACHE_ENABLED
    if cache:
        key = _hash_feeds(path, ready, f"seed={seed}")
        cpath = os.path.join(CACHE_DIR, f"{role}-{key}.npz")
        if os.path.isfile(cpath):
            try:
                with np.load(cpath) as z:
                    STATS["cache_hits"] += 1
                    STATS["runs"].append({"role": role, "seconds": 0.0, "cached": True})
                    return {k: z[k] for k in z.files}
            except Exception:  # noqa: BLE001 - a corrupt cache entry is just recomputed
                pass
    import onnxruntime as ort

    if seed is not None:
        ort.set_seed(int(seed))
    t0 = time.time()
    names = outputs or [o.name for o in sess.get_outputs()]
    res = sess.run(names, ready)
    out = dict(zip(names, res))
    STATS["runs"].append({"role": role, "seconds": round(time.time() - t0, 3), "cached": False, "dropped_feeds": dropped} if dropped else {"role": role, "seconds": round(time.time() - t0, 3), "cached": False})
    if cache and key:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = os.path.join(CACHE_DIR, f".{role}-{key}.{os.getpid()}.npz")
        np.savez(tmp, **out)
        os.replace(tmp, os.path.join(CACHE_DIR, f"{role}-{key}.npz"))
    return out


def input_names(path):
    return [i.name for i in session(path).get_inputs()]


def reset_stats():
    STATS["session_loads"].clear()
    STATS["runs"].clear()
    STATS["cache_hits"] = 0
