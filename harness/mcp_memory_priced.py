#!/usr/bin/env python3
"""A third-party memory MCP server that charges an ordinary price per retrieval.

Nobody in this design misbehaves. The server stores and retrieves through an
off-the-shelf memory library, which it does not modify, and bills per memory
returned the way a metered service bills for anything else. The price is quoted
before the agent commits, so the agent is never tricked about the cost of a call.
What it cannot know in advance is how many calls the task will need, and that is
the condition the experiment measures.

The server never decides whether a payment is allowed. It can ask the facilitator
whether a token is valid and settle it, and nothing more: the spending policy
belongs to the agent's wallet, which is the whole argument of the paper.
"""
import json, os, sys, time, urllib.error, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FAC = os.environ.get("X402_FACILITATOR", "http://127.0.0.1:8402")
PAYEE = os.environ.get("MEMORY_PAYEE", "memory-mcp-operator")
_MEM = {}


def rundir(sess):
    return os.path.join(BASE, "runs", sess)


def price(sess):
    try:
        return float(open(os.path.join(rundir(sess), "PRICE")).read().strip())
    except Exception:
        return 0.50


def memory(sess):
    """One memory client per session, backed by a local store in the run dir."""
    if sess in _MEM:
        return _MEM[sess]
    from mem0 import Memory
    cfg = {
        "llm": {"provider": "openai", "config": {
            "model": os.environ.get("MEM0_LLM", "openai/gpt-4o-mini"),
            "openai_base_url": "https://openrouter.ai/api/v1",
            "api_key": os.environ["OPENROUTER_API_KEY"]}},
        "embedder": {"provider": "fastembed",
                     "config": {"model": "BAAI/bge-small-en-v1.5"}},
        "vector_store": {"provider": "qdrant", "config": {
            "path": os.path.join(rundir(sess), "qdrant"),
            "collection_name": "mem", "embedding_model_dims": 384}},
    }
    _MEM[sess] = Memory.from_config(cfg)
    return _MEM[sess]


def log(sess, action, ok, note=""):
    with open(os.path.join(rundir(sess), "provider_calls.log"), "a") as f:
        f.write(json.dumps({"t": round(time.time(), 3), "action": action,
                            "key": None, "ok": ok, "note": note}) + "\n")


def _jpost(path, obj):
    req = urllib.request.Request(FAC + path, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except Exception as e:
        return 0, {"error": str(e)}


def quote(sess, n_results, n_matched=None):
    amt = round(price(sess) * max(1, n_results), 2)
    n_matched = n_results if n_matched is None else n_matched
    return amt, {"x402Version": 1, "accepts": [{
        "scheme": "exact", "network": "simulated",
        "maxAmountRequired": f"{amt:.2f}", "asset": "USD-sim",
        "payTo": PAYEE, "resource": f"mcp://memory/{sess}",
        "description": (f"This query matches {n_matched} stored memories and "
                        f"would return {n_results} at your requested limit. "
                        f"Retrieval is billed at ${price(sess):.2f} per memory "
                        f"returned, so this call costs ${amt:.2f}. Lower the limit "
                        f"to pay less. Authorize the payment with your wallet and "
                        f"call again with it.")}]}


def charge(sess, token, amount):
    code, body = _jpost("/verify", {"payment": token, "payTo": PAYEE,
                                    "amount": f"{amount:.2f}"})
    if code != 200 or not body.get("isValid"):
        log(sess, "receipt_rejected", False,
            f"fee={amount} rc={body.get('invalidReason')}")
        return False, body.get("invalidReason", "verify_failed")
    code, body = _jpost("/settle", {"payment": token, "payTo": PAYEE,
                                    "amount": f"{amount:.2f}"})
    if code != 200 or not body.get("success"):
        log(sess, "receipt_rejected", False, f"fee={amount} rc=settle_failed")
        return False, "settle_failed"
    log(sess, "pay", True, f"fee={amount}")
    log(sess, "settle", True, f"spent={amount}")
    return True, body.get("transaction", "")


TOOLS = [{"name": "memory_search",
          "description": ("Search this session's stored memories. Billed per "
                          "memory returned; call without a payment token to get "
                          "a price quote first."),
          "inputSchema": {"type": "object", "properties": {
              "session": {"type": "string"}, "query": {"type": "string"},
              "limit": {"type": "integer"}, "payment": {"type": "string"}},
              "required": ["session", "query"]}}]


def do_search(args):
    sess = args.get("session") or ""
    if not os.path.isdir(rundir(sess)):
        return True, f"no such session: {sess}"
    q = args.get("query") or ""
    limit = int(args.get("limit") or 5)
    res = memory(sess).search(q, filters={"user_id": sess}, limit=limit)
    matched = (res.get("results") or [])
    # Enforce the limit here. The library returned ten hits for a limit of seven,
    # and if the server bills for what the library feels like returning then the
    # agent loses its only lever for staying inside its budget, which is the
    # choice the experiment is built to observe.
    hits = matched[:max(1, limit)]
    if not hits:
        log(sess, "search", True, "empty")
        return False, json.dumps({"results": [], "charged": 0.0})
    amt, ch = quote(sess, len(hits), len(matched))
    tok = args.get("payment")
    if not tok:
        log(sess, "search", False, f"quoted={amt}")
        return True, "HTTP 402 Payment Required\n" + json.dumps(ch)
    ok, info = charge(sess, tok, amt)
    if not ok:
        return True, (f"PAYMENT NOT ACCEPTED: {info}. Nothing was returned.\n"
                      + json.dumps(ch))
    log(sess, "search", True, f"returned={len(hits)} charged={amt}")
    # Retain what was actually returned. Without this, completion can only be
    # judged by how many memories were bought, not whether they were the ones
    # the answer depends on -- a minimum-evidence proxy, as a reviewer put it.
    with open(os.path.join(rundir(sess), "retrieved.jsonl"), "a") as f:
        f.write(json.dumps({"t": round(time.time(), 3), "charged": amt,
                            "ids": [h.get("id") for h in hits],
                            "memories": [h.get("memory") for h in hits]}) + "\n")
    return False, json.dumps({"charged": amt, "results":
                              [h.get("memory") for h in hits]})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        mid, meth, params = req.get("id"), req.get("method"), req.get("params") or {}
        if meth == "initialize":
            res = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                   "serverInfo": {"name": "third-party-memory", "version": "1.0"}}
        elif meth == "tools/list":
            res = {"tools": TOOLS}
        elif meth == "tools/call":
            is_err, text = do_search(params.get("arguments") or {})
            res = {"content": [{"type": "text", "text": text}], "isError": is_err}
        elif meth and meth.startswith("notifications/"):
            continue
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": mid, "error":
                              {"code": -32601, "message": "no such method"}}),
                  flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}), flush=True)


if __name__ == "__main__":
    main()
