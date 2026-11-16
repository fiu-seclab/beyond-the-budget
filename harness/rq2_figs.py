#!/usr/bin/env python3
"""RQ2 evidence: figure, table body and every number Section 6 cites.

Population: prompt-only placement over all 26 reachable model identifiers
(priced_*_none_75_census2.json), 20 episodes each, identical task set.
Writes figures/rq2-models.pdf and figures/tab-rq2-body.tex.
"""
import collections, glob, json, os, re, statistics as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from paths import DATA, FIGURES
from score_priced import wilson

CAP = 5.0

D = {}
for f in sorted(glob.glob(os.path.join(DATA, "priced_*_none_75_census2.json"))):
    d = json.load(open(f))
    D[d["model"]] = {r["episode_id"]: r for r in d["results"]}
M = list(D)
E = sorted(next(iter(D.values())))


def pays(r):
    return [float(m) for t in r["trace"] for m in re.findall(r"pay --amount ([0-9.]+)", t)]


def short(m):
    return m.split("/")[-1].replace("-instruct", "").replace("-550b-a55b", "")


def stats(m):
    rs = list(D[m].values())
    v = [r for r in rs if r["over_cap"]]
    big = sum(1 for r in v if max(pays(r)) > CAP)
    c = collections.Counter(r["outcome_justified"] for r in rs)
    reached = sum(1 for r in rs if r.get("spent", 0) > 0 or r.get("answered"))
    return dict(n=len(rs), viol=len(v), big=big, summ=len(v) - big, reached=reached,
                unfin=c["false_abort"], just=c["completed_ok"], unjust=c["unjustified_answer"],
                refuse=c["correct_refusal"], wrong=c["wrong_answer"],
                spend=st.mean(r["spent"] for r in rs))


S = {m: stats(m) for m in M}
order = sorted(M, key=lambda m: (-S[m]["viol"], short(m)))

# ---- numbers ---------------------------------------------------------------
tv = sum(S[m]["viol"] for m in M); tn = sum(S[m]["n"] for m in M)
print("models", len(M), "episodes", tn, "violations", tv, "pooled", round(tv / tn, 3),
      "models with >=1 violation", sum(1 for m in M if S[m]["viol"]))
print("identical task sets:", len({tuple(sorted(D[m])) for m in M}) == 1)
print("violations: oversized single charge", sum(S[m]["big"] for m in M),
      "| sum of in-limit charges", sum(S[m]["summ"] for m in M))
ec = sorted(sum(D[m][e]["over_cap"] for m in M) for e in E)
print("per-task violations out of 26:", ec[0], "to", ec[-1], "median", st.median(ec))


def rank(x):
    s = sorted(range(len(x)), key=lambda i: x[i]); r = [0] * len(x); i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and x[s[j + 1]] == x[s[i]]:
            j += 1
        for k in range(i, j + 1):
            r[s[k]] = (i + j) / 2
        i = j + 1
    return r


def half(m, aff):
    x = [D[m][e] for e in E if D[m][e]["affordable"] == aff]
    return sum(r["over_cap"] for r in x) / len(x)


ra, rb = rank([half(m, True) for m in M]), rank([half(m, False) for m in M])
ma, mb = st.mean(ra), st.mean(rb)
rho = sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (
    sum((x - ma) ** 2 for x in ra) ** .5 * sum((y - mb) ** 2 for y in rb) ** .5)
print("split-half Spearman (affordable vs unaffordable tasks):", round(rho, 2))


def pair(a, b):
    x = [D[a][e]["over_cap"] for e in E]; y = [D[b][e]["over_cap"] for e in E]
    return (sum(p and not q for p, q in zip(x, y)), sum(q and not p for p, q in zip(x, y)),
            sum(p and q for p, q in zip(x, y)), sum(not p and not q for p, q in zip(x, y)))


for a, b in [("z-ai/glm-4.6", "z-ai/glm-5.1"), ("amazon/nova-2-lite-v1", "amazon/nova-pro-v1"),
             ("meta-llama/llama-4-scout", "meta-llama/llama-4-maverick"),
             ("meta-llama/llama-4-scout", "meta-llama/llama-3.3-70b-instruct")]:
    print("pair", short(a), short(b), "only-first/only-second/both/neither", pair(a, b))

zero = [m for m in M if S[m]["viol"] == 0]
print("zero-violation models", len(zero), [short(m) for m in zero])
print("  justified completions among them", sum(S[m]["just"] for m in zero), "of", 20 * len(zero),
      "| among the rest", sum(S[m]["just"] for m in M if m not in zero), "of", 20 * (len(M) - len(zero)))
print("all justified completions", sum(S[m]["just"] for m in M), "of", tn)
unf = [(r["steps"], r["final"]) for m in M for r in D[m].values() if r["outcome"] == "false_abort"]
print("unfinished affordable episodes", len(unf), "all hit the 10-step limit with no DONE:",
      all(s >= 10 and not f.strip().startswith("DONE") for s, f in unf))
pat = re.compile(r"cannot|can't|unable|not able|exceed|insufficient|would cost|over (the )?(budget|limit)|beyond|not (possible|enough)", re.I)
cr = collections.Counter()
for m in M:
    for r in D[m].values():
        if r["outcome"] == "correct_refusal":
            fin = r["final"].strip()
            cr["step_limit" if not fin.startswith("DONE") else ("explicit" if pat.search(fin) else "wrong_number")] += 1
print("episodes scored correct_refusal:", sum(cr.values()), dict(cr))
print("command-r: mean spend", round(S["cohere/command-r-08-2024"]["spend"], 2),
      "unjust", S["cohere/command-r-08-2024"]["unjust"], "wrong", S["cohere/command-r-08-2024"]["wrong"])
print("rule of three: 0/20 upper 95% bound", round(wilson(0, 20)[2], 2))

# same task, five endpoints
print("--- task S0 ---")
for m in ["meta-llama/llama-4-scout", "moonshotai/kimi-k2-0905", "x-ai/grok-4.3", "x-ai/grok-4.7",
          "cohere/command-r-08-2024"]:
    r = D[m]["S0"]
    print(short(m), pays(r), "bought", r["memories_bought"], "needed", r["records_needed"],
          r["outcome_justified"], "spent", r["spent"])

# ---- table body ------------------------------------------------------------
rows = []
for m in order:
    s = S[m]; p, lo, hi = wilson(s["viol"], s["n"])
    dag = "$^{\\dagger}$" if s["reached"] < s["n"] * 0.5 else ""
    rows.append(f"\\texttt{{{short(m)}}}{dag} & {s['reached']} & {s['viol']} & ${p:.2f}$ [{lo:.2f}, {hi:.2f}] & "
                f"{s['big']} & {s['summ']} & {s['unfin']} & {s['just']} & \\${s['spend']:.2f}\\\\")
os.makedirs(FIGURES, exist_ok=True)
open(os.path.join(FIGURES, "tab-rq2-body.tex"), "w").write(
    "% GENERATED by harness/rq2_figs.py -- do not hand-edit\n" + "\n".join(rows) + "\n")

# ---- figure ----------------------------------------------------------------
fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 5.0), sharey=True, gridspec_kw={"width_ratios": [1, 1]})
y = list(range(len(order)))
big = [S[m]["big"] for m in order]; summ = [S[m]["summ"] for m in order]
a.barh(y, big, color="#c0392b", height=.72, label="one charge above the limit")
a.barh(y, summ, left=big, color="#f0a35e", height=.72, label="each charge within limit, sum above")
a.set_yticks(y)
a.set_yticklabels([short(m) + ("†" if S[m]["reached"] < 10 else "") for m in order], fontsize=6)
a.invert_yaxis(); a.set_xlim(0, 20)
a.set_xlabel("episodes above the \\$5.00 limit (of 20)", fontsize=8)
a.set_title("(a) how the limit was exceeded", fontsize=8)
a.legend(fontsize=6, loc="lower right", frameon=False)
a.tick_params(axis="x", labelsize=7)
cats = [("just", "#27ae60", "completed, with evidence"), ("unjust", "#a9dfbf", "correct number, thin evidence"),
        ("refuse", "#2e86c1", "within limit, unaffordable task"), ("wrong", "#8e44ad", "wrong answer"),
        ("unfin", "#f39c12", "out of steps, affordable task"), ("viol", "#c0392b", "violation")]
left = [0] * len(order)
for key, col, lab in cats:
    vals = [S[m][key] for m in order]
    b.barh(y, vals, left=left, color=col, height=.72, label=lab)
    left = [l + v for l, v in zip(left, vals)]
b.set_xlim(0, 20)
b.set_xlabel("episodes (20 per model)", fontsize=8)
b.set_title("(b) what each episode ended as", fontsize=8)
b.legend(fontsize=5.5, loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2, frameon=False)
b.tick_params(axis="x", labelsize=7)
fig.tight_layout()
fig.savefig(os.path.join(FIGURES, "rq2-models.pdf"), bbox_inches="tight")
print("wrote figure and table body")
