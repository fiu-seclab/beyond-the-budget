#!/usr/bin/env python3
"""Replay every recorded agent payment trajectory against each settlement model.

Source of truth. An earlier version of this script read host/<RID>/ledger.jsonl.
Those directories are keyed by run id, and later arms (capture, reversal) reuse
the same run ids, so running them OVERWROTE the ledgers this table had been
computed from: the published figures were no longer reproducible from the
repository, and re-running the old script reported $700/$241 where the arm had
produced $620/$161. Every number here is now taken from the per-episode result
files, which are written once and never revisited. `host_requested` is the host's
own authorization ledger for that episode; `provider_calls` is the payee's record
of what it did with each receipt; the command trace supplies which receipt was
presented, in order.

No API calls: a settlement model consumes nothing but a trajectory of
authorization, presentation, redemption and refusal events.

Models
  debit          commit on authorization; nothing is ever returned.
  capture_agent  reserve on authorization, commit on redemption, release ONLY if
                 the agent explicitly voids.
  capture_expire reserve on authorization, commit on redemption, host releases
                 any reservation left unredeemed after the hold period.
  refund_reject  commit on authorization, reverse when the payee REFUSES a
                 presented receipt. A payee that is never asked keeps nothing but
                 the agent's budget stays consumed.
  refund_expire  commit on authorization, reverse on refusal or on expiry.
"""
import json, os, sys, glob, re

HERE = os.path.dirname(os.path.abspath(__file__))
RCPT = re.compile(r"--receipt\s+rcpt:([0-9a-f]+):")
# The void verb takes the receipt as its own argument, not after --receipt, so a
# pattern anchored on --receipt silently found no voids at all and reported
# agent-released capture as identical to debit in the very arm built to measure it.
VOID = re.compile(r"--void\s+rcpt:([0-9a-f]+):")

def trajectory(e):
    """(authorizations, redeemed, refused, voided, presented) for one episode.

    Redemption and refusal are paired by order: the receipts the agent presented
    appear in the command trace in sequence, and the payee's outcome for each
    appears in provider_calls in the same sequence. Pairing them is what recovers
    which nonce was refused, a fact the host's own ledger never sees -- the host
    records that it verified a signature, not that the payee then declined the
    charge for naming the wrong amount.
    """
    auth = [(r["nonce"], r.get("payee"), float(r.get("amount", 0.0)))
            for r in (e.get("host_requested") or [])
            if r.get("action") == "authorize" and r.get("ok") and r.get("nonce")]
    presented = [m.group(1) for t in (e.get("trace") or []) for m in [RCPT.search(t)] if m]
    outcomes = [p for p in (e.get("provider_calls") or [])
                if p.get("action") in ("pay", "receipt_rejected")]
    redeemed, refused = set(), set()
    for nonce, out in zip(presented, outcomes):
        (redeemed if out.get("ok") else refused).add(nonce)
    refused -= redeemed          # presented twice, accepted once: not a refusal
    voided = {m.group(1) for t in (e.get("trace") or [])
              for m in [VOID.search(t)] if m}
    # A void of an authorization the payee already redeemed is refused by the rail;
    # only a void of still-reserved authority releases anything.
    voided -= redeemed
    return auth, redeemed, refused, voided, set(presented)

def settle(model, auth, redeemed, refused, voided=frozenset()):
    """Returns (committed, captured). Captured is authority that bought service."""
    captured = sum(a for n, p, a in auth if n in redeemed)
    if model == "debit":
        committed = sum(a for n, p, a in auth)
    elif model == "capture_agent":
        committed = sum(a for n, p, a in auth if n not in voided)
    elif model == "capture_expire":
        committed = captured
    elif model == "refund_reject":
        committed = sum(a for n, p, a in auth if n not in refused)
    elif model == "refund_expire":
        committed = captured
    else:
        raise ValueError(model)
    return committed, captured

MODELS = ["debit", "capture_agent", "capture_expire", "refund_reject", "refund_expire"]

def main(pattern="openmodel_*_P1H.json"):
    tot = {m: [0.0, 0.0, 0] for m in MODELS}
    silent = rejected = n_ep = 0
    for f in sorted(glob.glob(os.path.join(HERE, pattern))):
        d = json.load(open(f))
        for e in d["results"]:
            if not e.get("reached_decision"):
                continue
            auth, redeemed, refused, voided, presented = trajectory(e)
            if not auth:
                continue
            n_ep += 1
            for nonce, payee, amt in auth:
                if nonce in redeemed:
                    continue
                if nonce in refused:
                    rejected += 1
                else:
                    silent += 1
            for m in MODELS:
                c, cap = settle(m, auth, redeemed, refused, voided)
                tot[m][0] += c; tot[m][1] += cap; tot[m][2] += 1
    print(f"episodes replayed: {n_ep}   authorizations left unredeemed: "
          f"{silent + rejected} (payee refused {rejected}, never presented {silent})\n")
    print(f"{'settlement model':16s} {'committed':>10s} {'captured':>9s} "
          f"{'wasted':>8s} {'recovered':>10s}")
    base = tot["debit"][0] - tot["debit"][1]
    for m in MODELS:
        c, cap, _ = tot[m]
        w = c - cap
        print(f"{m:16s} {c:10.2f} {cap:9.2f} {w:8.2f} "
              f"{(1 - w / base) * 100 if base else 0:9.0f}%")

if __name__ == "__main__":
    main(*sys.argv[1:])
