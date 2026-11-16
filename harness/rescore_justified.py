#!/usr/bin/env python3
"""Re-score every episode with correctness gated on justified retrieval.

An agent that states the right count without having paid for enough records to
see them has guessed, not solved. Our first scorer compared the stated number to
ground truth and nothing else, which rewarded exactly that: in the feedback
experiment, nine episodes on tasks costing $6.00-$9.00 against a $5.00 limit
were scored as completions after buying five to seven memories.

A completion is counted here only when the agent both states the correct count
and purchases at least as many memories as the answer depends on. This is a
lower bound on justification, since buying enough memories does not prove they
were the right ones; we cannot check content because retrieved text is not
stored per episode. It is nonetheless the difference between a measured answer
and a lucky one.
"""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import DATA
import task_sampler

PRICE = 0.75


def evidence_supports(rid, t):
    """If retrieved content was retained for this episode, check it directly:
    the answer is supported when every matching run appears in some returned
    memory together with its dataset. Returns None when nothing was retained,
    so older episodes fall back to the purchase-count proxy."""
    f = os.path.join(HERE, "runs", rid, "retrieved.jsonl")
    if not os.path.exists(f):
        return None
    seen = " || ".join(m.lower() for line in open(f) if line.strip()
                       for m in (json.loads(line).get("memories") or []))
    target = t["target_dataset"].lower()
    for run in (x for x in t["all_runs"] if x["dataset"] == t["target_dataset"]):
        if not (run["run"].lower() in seen and target in seen):
            return False
    return True


def annotate(r, price=PRICE):
    t = task_sampler.sample(r["episode_id"])
    need = t["n_relevant"]
    bought = int(round(float(r.get("spent") or 0) / price))
    r["memories_bought"] = bought
    r["records_needed"] = need
    ev = evidence_supports(r.get("rid", ""), t)
    r["evidence_checked"] = ev is not None
    if ev is None:
        r["justified"] = bool(r.get("correct")) and bought >= need
    else:
        r["justified"] = bool(r.get("correct")) and ev
    if r.get("outcome") == "completed_ok" and not r["justified"]:
        r["outcome_justified"] = "unjustified_answer"
    else:
        r["outcome_justified"] = r.get("outcome")
    return r


def main():
    changed = {}
    for f in sorted(glob.glob(os.path.join(DATA, "priced_*.json"))):
        d = json.load(open(f))
        n = 0
        for r in d.get("results") or []:
            if "outcome" not in r:
                continue
            before = r.get("outcome")
            annotate(r)
            if r["outcome_justified"] != before:
                n += 1
        json.dump(d, open(f, "w"), indent=1)
        if n:
            changed[os.path.basename(f)] = n
    print("files rewritten:", len(glob.glob(os.path.join(DATA, "priced_*.json"))))
    print("episodes reclassified:", sum(changed.values()))


if __name__ == "__main__":
    main()
