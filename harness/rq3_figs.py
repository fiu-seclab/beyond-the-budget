#!/usr/bin/env python3
"""RQ3 figures: per-model violations under three placements, outcome partition,
and where each prompt-only episode ends up under cumulative enforcement.

Writes figures/rq3-placement.pdf and rq3-transitions.pdf and prints the
numbers the RQ3 text cites.
"""
import collections, glob, json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from paths import DATA, FIGURES
from score_priced import CONTROLS

FIGS = FIGURES


def load(pat):
    out = {}
    for f in sorted(glob.glob(os.path.join(DATA, pat))):
        d = json.load(open(f))
        if d["model"] in CONTROLS and d.get("results"):
            for r in d["results"]:
                out[(d["model"], r["episode_id"])] = r
    return out


A = {"Prompt": load("priced_*_none_75_census2.json"),
     "Per charge": load("priced_*_per_charge_75_grid.json"),
     "Cumulative": load("priced_*_cumulative_75_grid.json")}
keys = set.intersection(*[set(v) for v in A.values()])
assert len(keys) == 120 and all(len(v) == 120 for v in A.values())
short = lambda m: m.split("/")[-1].replace("-instruct", "").replace("-550b-a55b", "")

print("outcome_justified by placement")
for p, rows in A.items():
    c = collections.Counter(r["outcome_justified"] for r in rows.values())
    order_out = ["overspend", "completed_ok", "unjustified_answer",
                 "correct_refusal", "wrong_answer", "false_abort"]
    print(" ", p, " ".join(f"{k}={c[k]}" for k in order_out), "n", len(rows))

viol = {m: [sum(r["over_cap"] for k, r in A[p].items() if k[0] == m) for p in A] for m in CONTROLS}
print("violations by model (prompt, per-charge, cumulative):", {short(m): v for m, v in viol.items()})

CATS = [("completed_ok", "#27ae60", "completed, with evidence"),
        ("unjustified_answer", "#a9dfbf", "correct number, thin evidence"),
        ("correct_refusal", "#2e86c1", "within limit, unaffordable task"),
        ("wrong_answer", "#8e44ad", "wrong answer"),
        ("false_abort", "#f39c12", "out of steps, affordable task"),
        ("overspend", "#c0392b", "violation")]

# ---- Figure 1: placement ----------------------------------------------------
fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 2.6), gridspec_kw={"width_ratios": [1.15, 1]})
order = sorted(CONTROLS, key=lambda m: -viol[m][0])
cols = {"Prompt": "#c0392b", "Per charge": "#e59866", "Cumulative": "#1f618d"}
for i, m in enumerate(order):
    v = viol[m]
    a.plot([min(v), max(v)], [i, i], c="#bbb", lw=1.2, zorder=1)
    for (p, c), x in zip(cols.items(), v):
        a.scatter(x, i, s=30, c=c, zorder=3, label=p if i == 0 else None)
a.set_yticks(range(len(order)))
a.set_yticklabels([short(m) for m in order], fontsize=7)
a.invert_yaxis()
a.set_xlim(-1, 20)
a.set_xlabel("episodes above the \\$5.00 limit (of 20)", fontsize=8)
a.set_title("(a) violations by model and placement", fontsize=8)
a.legend(fontsize=6.5, loc="lower right", frameon=False)
a.tick_params(axis="x", labelsize=7)

names = list(A)
left = [0] * 3
for key, col, lab in CATS:
    vals = [sum(1 for r in A[p].values() if r["outcome_justified"] == key) for p in names]
    b.barh(range(3), vals, left=left, color=col, height=.62, label=lab)
    for i, (v, l) in enumerate(zip(vals, left)):
        if v >= 8:
            b.text(l + v / 2, i, str(v), ha="center", va="center", fontsize=6.5,
                   color="white" if key not in ("unjustified_answer",) else "#222")
    left = [l + v for l, v in zip(left, vals)]
b.set_yticks(range(3)); b.set_yticklabels(names, fontsize=7.5); b.invert_yaxis()
b.set_xlim(0, 120)
b.set_xlabel("episodes (120 per placement)", fontsize=8)
b.set_title("(b) how episodes end", fontsize=8)
b.tick_params(axis="x", labelsize=7)
b.legend(fontsize=5.5, loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2, frameon=False)
fig.tight_layout()
os.makedirs(FIGS, exist_ok=True)
fig.savefig(os.path.join(FIGS, "rq3-placement.pdf"), bbox_inches="tight")

# ---- Figure 2: transitions prompt -> cumulative -------------------------------
rows = [c for c in CATS][::-1]          # violation first
rkeys = ["overspend", "completed_ok", "unjustified_answer", "correct_refusal", "wrong_answer", "false_abort"]
ckeys = ["completed_ok", "unjustified_answer", "correct_refusal", "wrong_answer", "false_abort"]
lab = {k: l for k, _, l in CATS}
short_lab = {"overspend": "violation", "completed_ok": "completed", "unjustified_answer": "thin evidence",
             "correct_refusal": "within limit,\nunaffordable", "wrong_answer": "wrong answer",
             "false_abort": "out of steps"}
T = collections.Counter((A["Prompt"][k]["outcome_justified"], A["Cumulative"][k]["outcome_justified"]) for k in keys)
M = [[T[(r, c)] for c in ckeys] for r in rkeys]
fig, ax = plt.subplots(figsize=(3.45, 2.9))
mx = max(max(r) for r in M)
ax.imshow(M, cmap="Blues", vmin=0, vmax=mx * 1.15)
for i, r in enumerate(M):
    for j, v in enumerate(r):
        if v:
            ax.text(j, i, v, ha="center", va="center", fontsize=8, color="white" if v > mx * .55 else "#222",
                    fontweight="bold" if i == 0 else None)
ax.set_xticks(range(len(ckeys))); ax.set_xticklabels([short_lab[c] for c in ckeys], fontsize=6, rotation=35, ha="right")
ax.set_yticks(range(len(rkeys))); ax.set_yticklabels([short_lab[r].replace("\n", " ") for r in rkeys], fontsize=6.5)
ax.axhline(0.5, c="#c0392b", lw=1.2)
ax.set_xlabel("under cumulative enforcement", fontsize=7.5)
ax.set_ylabel("under prompt-only", fontsize=7.5)
ax.tick_params(length=0)
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "rq3-transitions.pdf"), bbox_inches="tight")

v56 = [(c, T[("overspend", c)]) for c in ckeys]
print("56 prompt violations under cumulative:", v56, "sum", sum(n for _, n in v56))
stay = sum(T[(r, r)] for r in rkeys)
print("episodes with the same outcome in both:", stay)
print("wrote figures")
