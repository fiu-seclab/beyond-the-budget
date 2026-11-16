#!/usr/bin/env python3
"""Stage one episode of the priced-retrieval experiment.

Writes the run directory, loads the sampled prior session into the memory
service so the service extracts whatever it extracts, records the price and the
ground-truth answer for scoring, and initialises the agent's wallet under the
cap placement being tested.
"""
import argparse, json, os, shutil, sys, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import task_sampler

FAC = os.environ.get("X402_FACILITATOR", "http://127.0.0.1:8402")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--episode-id", required=True)
    ap.add_argument("--price", type=float, default=0.50)
    ap.add_argument("--cap", type=float, default=5.00)
    ap.add_argument("--policy", default="cumulative",
                    choices=["none", "per_charge", "cumulative"])
    ap.add_argument("--fresh", action="store_true",
                    help="delete any existing run directory first")
    a = ap.parse_args()

    rd = os.path.join(BASE, "runs", a.run)
    if a.fresh and os.path.isdir(rd):
        shutil.rmtree(rd)
    os.makedirs(rd, exist_ok=True)
    task = task_sampler.sample(a.episode_id)
    open(os.path.join(rd, "PRICE"), "w").write(f"{a.price}\n")
    json.dump({"episode_id": a.episode_id, "question": task["question"],
               "answer": task["answer"], "n_relevant": task["n_relevant"],
               "price": a.price, "cap": a.cap, "policy": a.policy,
               "task_cost": task_sampler.cost(task, a.price),
               "affordable": task_sampler.cost(task, a.price) <= a.cap},
              open(os.path.join(rd, "task.json"), "w"), indent=1)

    # Load the prior session into the memory service. The service decides what to
    # extract; we never write memories ourselves.
    from mcp_memory_priced import memory
    m = memory(a.run)
    m.add(task["transcript"], user_id=a.run)

    body = json.dumps({"scope": a.run, "cap": a.cap, "policy": a.policy}).encode()
    req = urllib.request.Request(FAC + "/init", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()
    # A freshly initialised scope must hold no spending. If it does, this run id
    # is being reused and the episode would measure two runs pooled together.
    import urllib.request as _u
    with _u.urlopen(FAC + f"/state/{a.run}", timeout=20) as r:
        st = json.loads(r.read() or b"{}")
    if float(st.get("committed") or 0) or int(st.get("requests") or 0):
        raise SystemExit(f"scope {a.run} is not empty after init: {st}")
    n = len(m.get_all(filters={"user_id": a.run}).get("results") or [])
    print(json.dumps({"run": a.run, "memories_extracted": n,
                      "relevant_runs": task["n_relevant"],
                      "task_cost": task_sampler.cost(task, a.price),
                      "affordable": task_sampler.cost(task, a.price) <= a.cap,
                      "policy": a.policy}))


if __name__ == "__main__":
    main()
