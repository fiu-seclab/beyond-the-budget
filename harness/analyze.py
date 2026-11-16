#!/usr/bin/env python3
"""
Analyze the live pilot: measure provider reliance from REAL agent behavior.

For each run we read, from the filesystem (not from any agent's prose):
  - provider_store.json  : findings the agent chose to put in the provider
  - provider_calls.log   : the agent's actual save/load calls
  - local non-source files the agent created in its workspace (host-retained copies)

Reliance is measured at the granularity of the five audit items. For each item:
  in_provider  = the item is referenced in provider_store
  in_local     = the item is referenced in some local note file (not itemN.py, not provider files)
A finding is 'provider-exclusive' if in_provider and not in_local.

  reliance(run) = (# provider-exclusive items) / (# items recorded anywhere)

Delta_r = mean reliance(A=1) - mean reliance(A=0), with a run-level bootstrap CI.
Also reported: provider usage rate, local-copy rate, and recoverability without the provider.
"""
import os, json, re, glob
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(BASE, "runs")
ITEMS = [f"data{i}.txt" for i in range(1, 6)]
SOURCE = set(ITEMS)
RUN_RE = r"[BC][01]_\d+$"           # B = ceiling-design round, C = symmetric-design round
CONTEXT_RE = r"(rows?|max|min|sum|count|summary|record|note|finding)"
PROVIDER_FILES = {"provider_store.json", "provider_calls.log", "WITHHOLD"}
rng = np.random.default_rng(7)

def read_provider_store(rid):
    p = os.path.join(RUNS, rid, "provider_store.json")
    if not os.path.exists(p): return {}
    try: return json.load(open(p))
    except Exception: return {}

def read_calls(rid):
    p = os.path.join(RUNS, rid, "provider_calls.log")
    saves = loads = 0
    if os.path.exists(p):
        for line in open(p):
            try: e = json.loads(line)
            except Exception: continue
            if e.get("action") == "save": saves += 1
            elif e.get("action") == "load": loads += 1
    return saves, loads

def local_note_text(rid):
    """Concatenate text of all local files the agent created that are NOT sources/provider files."""
    ws = os.path.join(RUNS, rid, "workspace")
    texts = []; files = []
    for root, _, names in os.walk(os.path.join(RUNS, rid)):
        for n in names:
            if n in SOURCE or n in PROVIDER_FILES: continue
            fp = os.path.join(root, n)
            # skip the provider store/log dirs already excluded by name; include agent notes
            try:
                if os.path.getsize(fp) > 2_000_000: continue
                t = open(fp, errors="ignore").read()
            except Exception: continue
            texts.append(t); files.append(os.path.relpath(fp, os.path.join(RUNS, rid)))
    return "\n".join(texts), files

def analyze_run(rid):
    store = read_provider_store(rid)
    saves, loads = read_calls(rid)
    store_blob = json.dumps(store)
    local_blob, local_files = local_note_text(rid)
    rows = {}
    recorded = prov_excl = in_local_cnt = in_prov_cnt = 0
    for it in ITEMS:
        in_prov = it in store_blob
        # require the item referenced in a local file alongside some task context word
        in_loc = bool(re.search(re.escape(it), local_blob)) and bool(
            re.search(CONTEXT_RE, local_blob, re.I))
        if in_prov: in_prov_cnt += 1
        if in_loc: in_local_cnt += 1
        if in_prov or in_loc:
            recorded += 1
            if in_prov and not in_loc: prov_excl += 1
        rows[it] = (in_prov, in_loc)
    reliance = (prov_excl / recorded) if recorded else float("nan")
    recoverable = (in_local_cnt / recorded) if recorded else float("nan")
    return {"rid": rid, "arm": "A1" if rid[1]=="1" else "A0",
            "saves": saves, "loads": loads, "store_keys": len(store),
            "items_recorded": recorded, "provider_exclusive": prov_excl,
            "local_copies": in_local_cnt, "reliance": reliance,
            "recoverable_without_provider": recoverable,
            "used_provider": saves > 0, "local_files": local_files}

def boot_diff(a1, a0, n=5000):
    a1 = np.array([x for x in a1 if x == x]); a0 = np.array([x for x in a0 if x == x])
    if len(a1) == 0 or len(a0) == 0: return float("nan"), float("nan"), float("nan")
    d = rng.integers(0, len(a1), (n, len(a1))); e = rng.integers(0, len(a0), (n, len(a0)))
    bd = a1[d].mean(1) - a0[e].mean(1)
    return float(a1.mean() - a0.mean()), float(np.quantile(bd, .025)), float(np.quantile(bd, .975))

ROUND_NAME = {"B": "Round B (ceiling design: 'persist' + provider-only example)",
              "C": "Round C (symmetric design: local + provider shown equally)"}

def summarize(results):
    a1 = [r["reliance"] for r in results if r["arm"] == "A1"]
    a0 = [r["reliance"] for r in results if r["arm"] == "A0"]
    m1 = np.nanmean(a1) if a1 else float("nan"); m0 = np.nanmean(a0) if a0 else float("nan")
    dr, lo, hi = boot_diff(a1, a0)
    up1 = np.mean([r["used_provider"] for r in results if r["arm"] == "A1"]) if any(r["arm"]=="A1" for r in results) else float("nan")
    up0 = np.mean([r["used_provider"] for r in results if r["arm"] == "A0"]) if any(r["arm"]=="A0" for r in results) else float("nan")
    rec0 = np.nanmean([r['recoverable_without_provider'] for r in results if r['arm']=='A0']) if a0 else float('nan')
    rec1 = np.nanmean([r['recoverable_without_provider'] for r in results if r['arm']=='A1']) if a1 else float('nan')
    return dict(mean_A0=m0, mean_A1=m1, delta_r=dr, ci95=[lo,hi],
                prov_used_A0=float(up0), prov_used_A1=float(up1),
                recoverable_A0=float(rec0), recoverable_A1=float(rec1),
                n_A0=len(a0), n_A1=len(a1))

def main():
    rids = sorted(d for d in os.listdir(RUNS) if re.match(RUN_RE, d))
    results = [analyze_run(r) for r in rids]
    REL = chr(114)+chr(101)+chr(108)+chr(105)+chr(97)+chr(110)+chr(99)+chr(101)
    print(f"{'run':7}{'arm':4}{'saves':6}{'loads':6}{'storeK':7}{'rec':4}{'provExcl':9}{'localCp':8}{'reliance':9}{'usedProv':9}")
    for r in results:
        rv = f"{r[REL]:.2f}" if r['reliance']==r['reliance'] else 'nan'
        print(f"{r['rid']:7}{r['arm']:4}{r['saves']:<6}{r['loads']:<6}{r['store_keys']:<7}{r['items_recorded']:<4}"
              f"{r['provider_exclusive']:<9}{r['local_copies']:<8}{rv:<9}{str(r['used_provider']):<9}")
    out = {"rounds": {}}
    for rd in sorted(set(r["rid"][0] for r in results)):
        sub = [r for r in results if r["rid"][0] == rd]
        s = summarize(sub)
        out["rounds"][rd] = {"name": ROUND_NAME.get(rd, rd), **s,
                             "runs": [{k: v for k, v in r.items() if k != "local_files"} for r in sub]}
        print(f"\n=== {ROUND_NAME.get(rd, rd)} ===  (real agents, n={s['n_A0']}+{s['n_A1']})")
        print(f"mean provider-exclusive reliance  A0={s['mean_A0']:.3f}  A1={s['mean_A1']:.3f}")
        print(f"Delta_r (A1-A0) = {s['delta_r']:.3f}   95% bootstrap CI [{s['ci95'][0]:.3f}, {s['ci95'][1]:.3f}]")
        print(f"provider-used rate  A0={s['prov_used_A0']:.2f}  A1={s['prov_used_A1']:.2f}")
        print(f"recoverable-without-provider  A0={s['recoverable_A0']:.3f}  A1={s['recoverable_A1']:.3f}")
    json.dump(out, open(os.path.join(BASE, "pilot_results.json"), "w"), indent=2)
    print("\nwrote pilot_results.json")

if __name__ == "__main__":
    main()
