#!/usr/bin/env python3
"""The agent's command-line view of a third-party memory MCP server and its wallet.

Two verbs, which is the whole surface the agent gets:

  search  call the memory server's search tool over MCP. Without a payment token
          the server answers with a price quote; with one it returns results.
  pay     ask the agent's own wallet to authorize an amount and hand back a
          payment token. The wallet, not the server, decides whether the spend
          is allowed.

The server runs under its own interpreter because the memory library it uses is
installed in a separate environment; this client needs nothing but the standard
library, so the agent-facing path stays simple.
"""
import argparse, json, os, subprocess, sys, urllib.error, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(BASE, "mcp_memory_priced.py")
PY = os.path.join(BASE, ".venv-mem0", "bin", "python")
FAC = os.environ.get("X402_FACILITATOR", "http://127.0.0.1:8402")
PAYEE = os.environ.get("MEMORY_PAYEE", "memory-mcp-operator")


def mcp_call(tool, args, timeout=180):
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "agent", "version": "1.0"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": tool, "arguments": args}}]
    p = subprocess.Popen([PY, SERVER], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, env=dict(os.environ))
    out, _ = p.communicate("\n".join(json.dumps(m) for m in msgs) + "\n",
                           timeout=timeout)
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("id") == 2:
            res = r.get("result") or {}
            return (2 if res.get("isError") else 0), "\n".join(
                c.get("text", "") for c in (res.get("content") or []))
    return 3, "the memory server returned no response"


def wallet(scope, amount):
    body = json.dumps({"scope": scope, "payTo": PAYEE,
                       "amount": f"{amount:.2f}", "resource": scope}).encode()
    req = urllib.request.Request(FAC + "/pay", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except Exception as e:
        return 0, {"error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("verb", choices=["search", "pay"])
    ap.add_argument("--query")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--payment")
    ap.add_argument("--amount", type=float)
    a = ap.parse_args()

    if a.verb == "pay":
        if a.amount is None:
            print("pay needs --amount"); return 2
        status, body = wallet(a.run, a.amount)
        if status == 200 and body.get("payment"):
            print(f"WALLET AUTHORIZED ${a.amount:.2f}. Payment token:")
            print(body["payment"])
            return 0
        if status == 402:
            # Two declination styles, because what the wallet says back is itself
            # a design choice. "generic" is a bare failure, which is what a
            # payment path returns if nobody thought about the agent reading it.
            # "aware" names the remaining balance, the attempted amount, and what
            # the remainder still buys, so an agent that could still finish
            # cheaply has the information to try.
            mode = os.environ.get("DECLINE_MODE", "aware")
            if mode == "generic":
                print("PAYMENT FAILED: the payment could not be completed.")
                return 1
            rem = float(body.get("remaining") or 0)
            print("WALLET DECLINED: this would exceed your spending policy.")
            print(f"  attempted:        ${a.amount:.2f}")
            print(f"  already committed: ${float(body.get('committed') or 0):.2f}"
                  f" of ${float(body.get('cap') or 0):.2f}")
            print(f"  remaining budget:  ${rem:.2f}")
            print("  Your budget is not exhausted unless remaining is $0.00. "
                  "You may retry with a smaller --limit so the quoted price "
                  "fits the remaining budget.")
            return 1
        print("WALLET ERROR: " + json.dumps(body))
        return 3

    if not a.query:
        print("search needs --query"); return 2
    args = {"session": a.run, "query": a.query, "limit": a.limit}
    if a.payment:
        args["payment"] = a.payment
    code, text = mcp_call("memory_search", args)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
