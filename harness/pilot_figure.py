#!/usr/bin/env python3
"""Plot the real-agent pilot: provider-exclusive reliance by arm, both rounds."""
import json, os
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.abspath(__file__))
res = json.load(open(os.path.join(BASE, "pilot_results.json")))
OUT = os.path.normpath(os.path.join(BASE, "..", "..", "paper", "figs"))
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({"figure.dpi":130,"savefig.dpi":200,"font.size":10,
    "axes.titlesize":11,"axes.titleweight":"bold","axes.spines.top":False,
    "axes.spines.right":False,"axes.grid":True,"grid.alpha":0.25,
    "font.family":"DejaVu Sans","pdf.fonttype":42})
NEUT="#4C78A8"; ADV="#E45756"; GREY="#8a8f98"
rng=np.random.default_rng(1)

fig,axes=plt.subplots(1,2,figsize=(9.6,4.0),sharey=True)
titles={"B":"Round B — ceiling design\n('persist' + provider-only example)",
        "C":"Round C — symmetric design\n(local + provider shown equally)"}
for ax,rd in zip(axes,["B","C"]):
    r=res["rounds"][rd]
    a0=[x["reliance"] for x in r["runs"] if x["arm"]=="A0"]
    a1=[x["reliance"] for x in r["runs"] if x["arm"]=="A1"]
    ax.bar([0,1],[np.mean(a0),np.mean(a1)],color=[NEUT,ADV],alpha=0.55,
           edgecolor="#1a1a2e",width=0.6,zorder=2)
    for xi,vals,c in [(0,a0,NEUT),(1,a1,ADV)]:
        ax.scatter(xi+rng.uniform(-0.12,0.12,len(vals)),vals,s=70,color=c,
                   edgecolor="#1a1a2e",zorder=4,linewidth=0.8)
    dr=r["delta_r"]; ci=r["ci95"]
    ax.set_xticks([0,1]); ax.set_xticklabels(["neutral\nA=0","encouraging\nA=1"])
    ax.set_ylim(-0.05,1.12); ax.set_title(titles[rd],fontsize=9.8)
    ax.annotate(f"Δr = {dr:.2f}\n95% CI [{ci[0]:.2f}, {ci[1]:.2f}]",
                xy=(0.5,1.03),ha="center",fontsize=8.6,
                color=(GREY if rd=="B" else ADV),fontweight="bold")
axes[0].set_ylabel("provider-exclusive reliance\n(share of task-critical state kept only in provider)")
fig.suptitle("Real-agent pilot (Claude, n=4+4/arm): does provider wording shift reliance?",
             fontsize=11,fontweight="bold",y=1.04)
fig.text(0.5,0.005,"Round B had a ceiling (both arms nudged to the provider). Round C, with a fair choice, shows the predicted "
         "direction: encouraging\nwording raised reliance 0.50→1.00 and eliminated independent recoverability. n=4/arm → directional, not conclusive.",
         ha="center",fontsize=7.1,style="italic",color=GREY)
fig.tight_layout(rect=[0,0.04,1,0.97])
fig.savefig(os.path.join(OUT,"fig_pilot.pdf"),bbox_inches="tight")
fig.savefig(os.path.join(OUT,"fig_pilot.png"),bbox_inches="tight")
print("wrote fig_pilot.{pdf,png} ->",OUT)
