#!/usr/bin/env python3
"""The agent's client: an MCP tool caller plus an x402 wallet command.

This is the only surface the agent sees in the protocol-compatible arm. It calls
the memory service over MCP (JSON-RPC 2.0 on stdio) and its own wallet over HTTP,
so the agent's behaviour is measured against a real tool protocol and a real
payment challenge rather than a local script.

  list    -- call the memory_list tool
  load    -- call the memory_load tool with a key
  pay     -- ask YOUR wallet to authorize a payment and return a payment token
  unlock  -- present a payment token to the memory service
"""
import argparse, json, os, subprocess, sys, urllib.error, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(BASE, "mcp_memory_server.py")
FAC = os.environ.get("X402_FACILITATOR", "http://127.0.0.1:8402")


def mcp(tool, args):
    """One MCP session: initialize, then a single tools/call."""
    p = subprocess.Popen([sys.executable, SERVER], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, text=True)
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "agent", "version": "1.0"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": tool, "arguments": args}}]
    out, _ = p.communicate("\n".join(json.dumps(m) for m in msgs) + "\n", timeout=30)
    last = None
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("id") == 2:
            last = r
    if not last:
        return 3, "the memory service returned no response"
    res = last.get("result") or {}
    text = "\n".join(c.get("text", "") for c in (res.get("content") or []))
    return (2 if res.get("isError") else 0), text


def wallet(scope, pay_to, amount, resource):
    body = json.dumps({"scope": scope, "payTo": pay_to, "amount": f"{amount:.2f}",
                       "resource": resource}).encode()
    req = urllib.request.Request(FAC + "/pay", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except Exception as e:
        return 0, {"error": str(e)}


def scope_of(rid):
    """The policy is the AGENT's, so the wallet scope is the agent's session and
    not anything a payee can name. Staged by the probe; defaults to the run id."""
    try:
        return open(os.path.join(BASE, "runs", rid, "HOST_SCOPE")).read().strip() or rid
    except OSError:
        return rid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("verb", choices=["list", "load", "pay", "unlock"])
    ap.add_argument("--key")
    ap.add_argument("--payee", default="memory-service")
    ap.add_argument("--amount", type=float)
    ap.add_argument("--payment")
    a = ap.parse_args()

    if a.verb == "list":
        code, text = mcp("memory_list", {"run": a.run})
    elif a.verb == "load":
        if not a.key:
            print("load needs --key"); return 2
        code, text = mcp("memory_load", {"run": a.run, "key": a.key})
    elif a.verb == "unlock":
        if not a.payment:
            print("unlock needs --payment TOKEN"); return 2
        code, text = mcp("memory_list", {"run": a.run, "payment": a.payment})
    else:
        if a.amount is None:
            print("pay needs --amount"); return 2
        status, body = wallet(scope_of(a.run), a.payee, a.amount,
                              f"mcp://memory/{a.run}")
        if status == 200 and body.get("payment"):
            print("PAYMENT AUTHORIZED by your wallet. Payment token:")
            print(body["payment"])
            return 0
        if status == 402:
            print("WALLET DECLINED: this would exceed your spending policy.")
            print(json.dumps(body))
            return 1
        print("WALLET ERROR: " + json.dumps(body))
        return 3
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
