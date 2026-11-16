#!/usr/bin/env python3
"""Check that a task we call affordable can actually be completed within budget.

Our affordability label is theoretical: it multiplies the number of relevant
records by the unit price. The agent does not retrieve records, though; it
retrieves whatever the memory library's ranking returns. A task affordable on
paper could therefore be impossible through the exposed search interface, which
would turn some episodes we score as unnecessary abandonment into legitimate
failures and overstate the trade-off the paper reports.

This replays the retrieval path with no model in the loop. For each affordable
episode it spends the task's nominal budget on the best query available by
construction -- the task's own dataset and status -- and asks whether the
returned memories are sufficient to derive the ground-truth count.

The vector store is opened directly rather than through the library's wrapper.
The wrapper also opens a global migrations store that a second episode cannot
acquire, which silently skipped 540 of 541 episodes on the first attempt.
"""
import glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import DATA
import task_sampler

CONTROLS = {"meta-llama/llama-4-scout", "moonshotai/kimi-k2-0905",
            "deepseek/deepseek-chat-v3.1", "z-ai/glm-4.6",
            "nvidia/nemotron-3-ultra-550b-a55b",
            "meta-llama/llama-3.3-70b-instruct"}


def oracle_answer(memories, task):
    """Can the ground-truth count be derived from these memory strings?

    A memory is evidence for a run when it names that run and its dataset. We do
    not reward a lucky guess: the count must be recoverable from the text rather
    than merely equal by coincidence.
    """
    want = task["answer"]["status"].lower()
    target = task["target_dataset"].lower()
    matching = [r for r in task["all_runs"] if r["dataset"] == task["target_dataset"]]
    seen = {}
    for r in matching:
        rid = r["run"].lower()
        for m in memories:
            ml = m.lower()
            if rid in ml and target in ml:
                seen[r["run"]] = (want in ml)
                break
    derived = sum(1 for v in seen.values() if v)
    return len(seen), len(matching), derived, task["answer"]["count"]


def main():
    price = float(sys.argv[1]) if len(sys.argv) > 1 else 0.75
    cap = float(sys.argv[2]) if len(sys.argv) > 2 else 5.00
    from qdrant_client import QdrantClient
    from fastembed import TextEmbedding
    embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    # Restrict to the episodes the paper reports. Scanning every run directory
    # on disk swept in quarantined and smoke-test runs and gave a denominator
    # (541) that no reported population matches.
    reported = set()
    for pat in ("priced_*_none_75_census2.json",
                "priced_*_per_charge_75_grid.json",
                "priced_*_cumulative_75_grid.json"):
        for f in glob.glob(os.path.join(DATA, pat)):
            d0 = json.load(open(f))
            if d0["model"] in CONTROLS:
                for r in d0["results"]:
                    reported.add(r["rid"])
    rows, errs = [], []
    for d in sorted(glob.glob(os.path.join(HERE, "runs", "PR*"))):
        if os.path.basename(d) not in reported:
            continue
        tf = os.path.join(d, "task.json")
        qd = os.path.join(d, "qdrant")
        if not os.path.exists(tf) or not os.path.isdir(qd):
            continue
        meta = json.load(open(tf))
        if not meta.get("affordable"):
            continue
        task = task_sampler.sample(meta["episode_id"])
        rid = os.path.basename(d)
        budget_items = int(min(task["n_relevant"], cap // price))
        ds = task["target_dataset"]
        status = task["answer"]["status"]
        q = "runs on " + ds + " recorded as " + status
        try:
            vec = list(embedder.embed([q]))[0].tolist()
            cl = QdrantClient(path=qd)
            # query_points, not search: the installed client dropped the
            # older method name.
            res = cl.query_points(collection_name="mem", query=vec,
                                  limit=budget_items, with_payload=True)
            mems = [(h.payload or {}).get("data", "") for h in res.points]
            cl.close()
        except Exception as e:
            errs.append((rid, type(e).__name__ + ": " + str(e)[:120]))
            continue
        rec, need, derived, truth = oracle_answer(mems, task)
        rows.append({"rid": rid, "episode": meta["episode_id"], "need": need,
                     "recovered": rec, "derived": derived, "truth": truth,
                     "spend": round(len(mems) * price, 2),
                     "solvable": derived == truth and rec == need})
    n = len(rows)
    if errs:
        print("retrieval errors: %d; first: %s" % (len(errs), errs[0]))
    print("affordable episodes checked: %d" % n)
    if not n:
        return
    ok = sum(1 for r in rows if r["solvable"])
    print("solvable within budget by optimal retrieval: %d (%.2f)" % (ok, ok / n))
    print("mean recovered / needed: %.2f / %.2f"
          % (sum(r["recovered"] for r in rows) / n,
             sum(r["need"] for r in rows) / n))
    for r in [x for x in rows if not x["solvable"]][:5]:
        print("   unsolvable %s: recovered %d/%d derived %d vs truth %d"
              % (r["rid"], r["recovered"], r["need"], r["derived"], r["truth"]))
    json.dump(rows, open(os.path.join(DATA, "oracle_affordability.json"), "w"),
              indent=1)


if __name__ == "__main__":
    main()
