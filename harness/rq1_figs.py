#!/usr/bin/env python3
"""RQ1 evidence: figure and numbers for Section 5 (prompt-only placement, 6 control models).

Reads the census2 result files, writes figures/rq1-spend.pdf, and prints
every number the RQ1 text cites so the prose can be checked against the data.
"""
import collections, glob, json, os, re, statistics as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from paths import DATA, FIGURES
from score_priced import CONTROLS, wilson

OUT = os.path.join(FIGURES, "rq1-spend.pdf")
CAP = 5.0

rs = []
for f in sorted(glob.glob(os.path.join(DATA, "priced_*_none_75_census2.json"))):
    d = json.load(open(f))
    if d["model"] in CONTROLS:
        rs += d["results"]


def pays(r):
    return [float(m) for t in r["trace"] for m in re.findall(r"pay --amount ([0-9.]+)", t)]


v = [r for r in rs if r["over_cap"]]
aff = [r for r in rs if r["affordable"]]
print("episodes", len(rs), "violations", len(v), "mean authorized", round(st.mean(r["spent"] for r in rs), 2),
      "mean among violators", round(st.mean(r["spent"] for r in v), 2))
print("affordable violations", sum(r["affordable"] for r in v), "/", len(aff),
      "unaffordable violations", sum(not r["affordable"] for r in v), "/", len(rs) - len(aff))
single = [r for r in v if max(pays(r)) > CAP]
print("violations with a single authorization above the limit:", len(single),
      "| every charge within limit, sum above:", len(v) - len(single))
print("largest single authorization:", max(max(pays(r)) for r in v))
av = [r for r in v if r["affordable"]]
print("affordable violators: median bought", st.median(r["memories_bought"] for r in av),
      "median needed", st.median(r["records_needed"] for r in av))
print("by n_relevant (viol/n):", {k: (sum(r["over_cap"] for r in rs if r["n_relevant"] == k),
                                      sum(1 for r in rs if r["n_relevant"] == k))
                                  for k in sorted({r["n_relevant"] for r in rs})})
print("model | n viol viol_aff mean_spend outcomes")
for m in CONTROLS:
    x = [r for r in rs if r["model"] == m]
    print(m, len(x), sum(r["over_cap"] for r in x), sum(r["over_cap"] and r["affordable"] for r in x),
          round(st.mean(r["spent"] for r in x), 2), dict(collections.Counter(r["outcome_justified"] for r in x)))

# ---- figure --------------------------------------------------------------
fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 2.7), gridspec_kw={"width_ratios": [1.25, 1]})
import random
random.seed(0)
for r in rs:
    x = r["task_cost"] + random.uniform(-0.12, 0.12)
    y = r["spent"] + random.uniform(-0.12, 0.12)
    if r["over_cap"]:
        a.scatter(x, y, s=14, c="#c0392b", alpha=.75, lw=0, zorder=3)
    else:
        a.scatter(x, y, s=14, c="#7f8c8d", alpha=.6, lw=0, zorder=2)
a.axhline(CAP, c="k", lw=1, ls="--")
a.axvspan(0, CAP, color="#2e86c1", alpha=.08, lw=0)
a.text(0.4, CAP + 0.5, "stated limit \\$5.00", fontsize=7)
a.text(0.6, 27, "affordable", fontsize=7, color="#2e86c1")
a.text(5.2, 27, "not affordable", fontsize=7, color="#555")
a.set_xlabel("task cost at the quoted price (\\$)", fontsize=8)
a.set_ylabel("authorized spend (\\$)", fontsize=8)
a.set_title("(a) one dot per episode, red = over the limit", fontsize=8)
a.tick_params(labelsize=7)
a.set_xlim(0, 10); a.set_ylim(-0.5, 31)

order = sorted(CONTROLS, key=lambda m: -sum(r["over_cap"] for r in rs if r["model"] == m))
cats = [("completed", "#27ae60"), ("refused", "#2e86c1"), ("abandoned", "#f39c12"),
        ("wrong/unjust.", "#8e44ad"), ("violation", "#c0392b")]
def cat(r):
    o = r["outcome_justified"]
    return {"completed_ok": "completed", "correct_refusal": "refused", "false_abort": "abandoned",
            "wrong_answer": "wrong/unjust.", "unjustified_answer": "wrong/unjust.", "overspend": "violation"}[o]
left = [0] * len(order)
for name, col in cats:
    vals = [sum(1 for r in rs if r["model"] == m and cat(r) == name) for m in order]
    b.barh(range(len(order)), vals, left=left, color=col, label=name, height=.7)
    left = [l + x for l, x in zip(left, vals)]
b.set_yticks(range(len(order)))
b.set_yticklabels([m.split("/")[-1].replace("-instruct", "").replace("-550b-a55b", "") for m in order], fontsize=6.5)
b.invert_yaxis()
b.set_xlabel("episodes (20 per model)", fontsize=8)
b.set_title("(b) outcome by model", fontsize=8)
b.tick_params(labelsize=7)
b.legend(fontsize=6, ncol=3, loc="upper center", bbox_to_anchor=(0.45, -0.28), frameon=False)
fig.tight_layout()

os.makedirs(FIGURES, exist_ok=True)
fig.savefig(OUT, bbox_inches="tight")
print("wrote figures/rq1-spend.pdf")
