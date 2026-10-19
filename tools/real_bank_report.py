"""render a standard set of phrases with every real bank under ./banks, inspect them, write a report.

per bank: probe --check summary, then four phrases (a scale on one vowel, a line with tricky
phonemes for the bank's language, a melisma, a phrase with rests), each inspected. diffsinger
banks with several languages also sing the tricky line in each language they have a line for.

usage: python tools/real_bank_report.py [bank-name-filter]   -> docs/real_banks.md, out/real_banks/
"""

import json
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "out", "real_banks")

PHRASES = {
    "ja": {
        "scale": "あ:C4:1/2 あ:D4:1/2 あ:E4:1/2 あ:F4:1/2 あ:G4:1/2 あ:A4:1/2 あ:B4:1/2 あ:C5:1",
        "tricky": "きゃ:E4:1/2 っ:E4:1/4 と:E4:1/4 しゅ:G4:1/2 ん:G4:1/2 ぎょ:A4:1/2 う:A4:1/2 ふぁ:G4:1/2 ゔぃ:E4:1",
        "melisma": "あ:C4:1/2 +:D4:1/4 +:E4:1/4 +:F4:1/4 +:E4:1/4 +:D4:1/2 い:C4:1",
        "rests": "さ:E4:1/2 く:G4:1/2 r:1/2 ら:A4:1 r:1 さ:G4:1/2 く:E4:1/2 ら:D4:1",
    },
    "en": {
        "scale": "ah:C4:1/2 ah:D4:1/2 ah:E4:1/2 ah:F4:1/2 ah:G4:1/2 ah:A4:1/2 ah:B4:1/2 ah:C5:1",
        "tricky": "strength:E4:1/2 through:G4:1/2 the:A4:1/2 rhythm:G4:1 of:E4:1/2 twelfths:D4:1",
        "melisma": "love:C4:1/2 +:D4:1/4 +:E4:1/4 +:F4:1/2 you:E4:1",
        "rests": "hello:E4:1 r:1/2 world:G4:1 r:1 good:A4:1/2 night:G4:1",
    },
    "zh": {"tricky": "我:E4:1/2 爱:G4:1/2 唱:A4:1/2 歌:G4:1 你:E4:1/2 好:D4:1"},
    "ko": {"tricky": "사:E4:1/2 랑:G4:1/2 해:A4:1/2 요:G4:1 노:E4:1/2 래:D4:1"},
    "es": {"tricky": "ca:E4:1/2 ri:G4:1/2 ño:A4:1/2 can:G4:1 tar:E4:1/2 mar:D4:1"},
    "de": {"tricky": "ich:E4:1/2 lie:G4:1/2 be:A4:1/2 dich:G4:1 schön:E4:1/2 sein:D4:1"},
}


def bank_lang(probe):
    if probe["type"] == "diffsinger":
        return probe.get("languages") or ["ja"]
    style = probe.get("reclist", {}).get("style", "")
    name = (probe.get("name") or "") + " " + os.path.basename(probe["bank"])
    if "ENG" in name.upper() or "ENGLISH" in name.upper() or "ARPA" in name.upper() or style.startswith(("diphone", "vccv")):
        return ["en"]
    return ["ja"]


def run_bank(path, cli):
    from warble.probe import probe

    p = probe(path, check=True)
    entry = {"bank": os.path.relpath(path, ROOT), "type": p["type"], "name": p.get("name"),
             "issues": p["issue_summary"]["by_severity"], "renders": []}
    if p["type"] == "utau":
        entry["reclist"] = p["reclist"]["style"]
    langs = bank_lang(p)
    primary = "ja" if "ja" in langs else langs[0]
    jobs = [(primary, k, v) for k, v in PHRASES.get(primary, {}).items()]
    if p["type"] == "diffsinger":
        for lg in langs:
            if lg != primary and lg in PHRASES and "tricky" in PHRASES[lg]:
                jobs.append((lg, "tricky", PHRASES[lg]["tricky"]))
    for lang, kind, expr in jobs:
        tag = f"{os.path.basename(path)}_{lang}_{kind}".replace(" ", "_")
        wav = os.path.join(OUT, tag + ".wav")
        rep = cli(["sing", "-e", expr, "--bank", path, "--lang", lang, "--bpm", "100", "--seed", "1", "--allow-unknown", "-o", wav])
        r = {"lang": lang, "phrase": kind}
        if "error" in rep:
            r["error"] = f"{rep['error']}: {rep.get('message', '')}"[:300]
            entry["renders"].append(r)
            continue
        r["phonemes"] = " | ".join(ph["phonemes"] for ph in rep["phrases"])[:200]
        r["unknown"] = [u["lyric"] for u in rep.get("unknown_lyrics", [])]
        ins = cli(["inspect", wav, "--no-images"])
        if "error" in ins:
            r["error"] = ins["message"]
        else:
            ov = ins.get("overall") or {}
            r.update({
                "median_abs_cents": ov.get("median_abs_cents_error"), "within_20c_pct": ov.get("mean_within_20c_pct"),
                "artifacts": {k: v for k, v in ins["artifact_counts"].items() if k != "robotic_flatness"},
                "lufs": ins["summary"]["lufs"],
                "intelligibility": (ins.get("intelligibility") or {}).get("syllable_accuracy_pct"),
                "heard": " / ".join(ph["heard"][:40] for ph in (ins.get("intelligibility") or {}).get("phrases", [])) or None,
            })
        entry["renders"].append(r)
    return entry


def main():
    import contextlib
    import io

    from warble.bank import common
    from warble.cli import main as cli_main

    def cli(argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli_main(argv)
        return json.loads(buf.getvalue())

    os.makedirs(OUT, exist_ok=True)
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    banks = [b for b in common.scan(os.path.join(ROOT, "banks")) if flt in b]
    results = []
    for b in banks:
        print(f"== {b}", file=sys.stderr)
        try:
            results.append(run_bank(b, cli))
        except Exception as e:  # noqa: BLE001
            results.append({"bank": os.path.relpath(b, ROOT), "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]})
    with open(os.path.join(ROOT, "docs", "real_banks.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    lines = ["# real bank report", "", "generated by `python tools/real_bank_report.py`: every bank under ./banks probes, then sings "
             "four phrases (seed 1, 100 bpm) that `inspect` measures. pitch columns compare the render with its own intended curve; "
             "intelligibility is the share of syllables a local whisper model recognized (short phrases make it noisy).", ""]
    for e in results:
        lines.append(f"## {e.get('name') or e['bank']}")
        lines.append("")
        if e.get("error"):
            lines += [f"failed: {e['error']}", ""]
            continue
        lines.append(f"`{e['bank']}`: {e['type']}" + (f", reclist {e['reclist']}" if e.get("reclist") else "") + f"; probe --check: {e['issues']}")
        lines += ["", "| lang | phrase | phonemes | median cents | within 20c | artifacts | intelligibility | heard |", "|---|---|---|---|---|---|---|---|"]
        for r in e["renders"]:
            if r.get("error"):
                lines.append(f"| {r['lang']} | {r['phrase']} | error: {r['error']} | | | | | |")
                continue
            unk = f" (unknown: {', '.join(r['unknown'])})" if r.get("unknown") else ""
            lines.append(f"| {r['lang']} | {r['phrase']} | {r['phonemes'][:80]}{unk} | {r['median_abs_cents']} | {r['within_20c_pct']}% | "
                         f"{r['artifacts'] or 'none'} | {r['intelligibility'] if r['intelligibility'] is not None else ''} | {r.get('heard') or ''} |")
        lines.append("")
    with open(os.path.join(ROOT, "docs", "real_banks.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote docs/real_banks.md", file=sys.stderr)


if __name__ == "__main__":
    main()
