#!/usr/bin/env python3
"""An x402-shaped payment rail: agent wallet plus facilitator, over HTTP.

A reviewer objected, correctly, that the settlement results were produced by a
local command-line simulator rather than by anything protocol-compatible. This
implements the x402 request/authorize/verify/settle flow over real HTTP with
simulated funds, so the authorization-scope and abandoned-hold findings can be
re-measured without changing their semantics.

Roles, kept separate on purpose:
  /pay      the AGENT's wallet. Holds the policy cap and signs a payment payload.
            This is the only component that may decide an amount is allowed, and
            it counts spend cumulatively across every payee in the session.
  /verify   the FACILITATOR. Checks the signature, that the nonce is unused, and
            that the payload is bound to the payee and amount presented.
  /settle   the FACILITATOR. Consumes the nonce and records the transfer.

The payee is never given an endpoint that can authorize, which is the trust
boundary the paper argues for: the component that wants the money must not decide
the outcome.
"""
import base64, hashlib, hmac, json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "x402")
X402_VERSION = 1
LOCK = threading.Lock()


def _dir(scope):
    d = os.path.join(STATE, scope)
    os.makedirs(d, exist_ok=True)
    return d


def _read(p, default=""):
    try:
        return open(p).read().strip()
    except OSError:
        return default


def init(scope, cap, key=None, policy="cumulative"):
    """policy is the experiment's manipulated variable.

    none       the wallet signs whatever it is asked for. The budget exists only
               as a sentence in the agent's prompt, which is how deployments
               express a spending limit today.
    per_charge the wallet refuses any SINGLE charge above the cap, which is the
               check a reviewer first reaches for and which cumulative spending
               walks straight through.
    cumulative the wallet refuses when total authorized spend would exceed the
               cap, counted across every payee in the session.
    """
    d = _dir(scope)
    open(os.path.join(d, "cap"), "w").write(str(float(cap)))
    open(os.path.join(d, "policy"), "w").write(policy)
    if not os.path.exists(os.path.join(d, "key")):
        open(os.path.join(d, "key"), "w").write(key or os.urandom(16).hex())
    # Truncate, do not append. Opening with "a" meant a reused scope inherited
    # every authorization from the previous run, so spend accumulated across
    # episodes that were supposed to be independent.
    open(os.path.join(d, "ledger.jsonl"), "w").close()
    return d


def _ledger(scope):
    """Rows for a scope, or none. A scope that was never initialised has no
    ledger file, and reading one raised inside the request handler, which looked
    from outside exactly like a dead server."""
    rows = []
    f = os.path.join(_dir(scope), "ledger.jsonl")
    if not os.path.exists(f):
        return rows
    for line in open(f, "r"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def _append(scope, row):
    with open(os.path.join(_dir(scope), "ledger.jsonl"), "a") as f:
        f.write(json.dumps(row) + "\n")


def _committed(scope):
    """Cumulative across every payee. A per-payee count is not a budget."""
    return sum(float(r.get("amount", 0.0)) for r in _ledger(scope)
               if r.get("ok") and r.get("action") == "authorize")


def _sign(scope, payload):
    key = _read(os.path.join(_dir(scope), "key")).encode()
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def pay(scope, pay_to, amount, resource=""):
    """Agent wallet: authorize and sign, or decline on the cumulative cap."""
    with LOCK:
        cap = float(_read(os.path.join(_dir(scope), "cap"), "0") or 0)
        policy = _read(os.path.join(_dir(scope), "policy"), "cumulative") or "cumulative"
        amount = float(amount)
        spent = _committed(scope)
        if policy == "none":
            over = False
        elif policy == "per_charge":
            over = amount > cap + 1e-9
        else:
            over = spent + amount > cap + 1e-9
        if over:
            _append(scope, {"t": time.time(), "action": "authorize", "ok": False,
                            "payee": pay_to, "amount": amount,
                            "reason": "cap_exceeded", "cap": cap,
                            "committed": spent})
            return 402, {"x402Version": X402_VERSION, "error": "cap_exceeded",
                         "cap": cap, "committed": spent, "requested": amount,
                         "remaining": round(max(0.0, cap - spent), 2)}
        nonce = os.urandom(8).hex()
        payload = {"x402Version": X402_VERSION, "scheme": "exact",
                   "network": "simulated", "payTo": pay_to,
                   "amount": f"{amount:.2f}", "asset": "USD-sim",
                   "resource": resource, "nonce": nonce, "scope": scope}
        payload["signature"] = _sign(scope, payload)
        _append(scope, {"t": time.time(), "action": "authorize", "ok": True,
                        "payee": pay_to, "amount": amount, "nonce": nonce,
                        "cap": cap, "committed": spent})
        token = base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode()).decode()
        return 200, {"x402Version": X402_VERSION, "payment": token}


def _decode(token):
    try:
        return json.loads(base64.b64decode(token.encode()))
    except Exception:
        return None


def verify(token, pay_to, amount):
    """Facilitator: signature, payee binding, amount binding, nonce freshness."""
    p = _decode(token)
    if not p or "signature" not in p or "scope" not in p:
        return 400, {"isValid": False, "invalidReason": "malformed_payload"}
    scope = p["scope"]
    sig = p.pop("signature")
    if not hmac.compare_digest(sig, _sign(scope, p)):
        return 402, {"isValid": False, "invalidReason": "bad_signature"}
    if p.get("payTo") != pay_to:
        return 402, {"isValid": False, "invalidReason": "payee_mismatch",
                     "payTo": p.get("payTo")}
    if abs(float(p.get("amount", 0)) - float(amount)) > 1e-9:
        return 402, {"isValid": False, "invalidReason": "amount_mismatch",
                     "amount": p.get("amount")}
    with LOCK:
        if any(r.get("action") == "settle" and r.get("nonce") == p["nonce"]
               for r in _ledger(scope)):
            return 402, {"isValid": False, "invalidReason": "nonce_already_used"}
    return 200, {"isValid": True, "payer": scope, "amount": p["amount"]}


def settle(token, pay_to, amount):
    code, body = verify(token, pay_to, amount)
    if code != 200:
        return code, body
    p = _decode(token)
    scope = p["scope"]
    with LOCK:
        _append(scope, {"t": time.time(), "action": "settle", "ok": True,
                        "payee": pay_to, "amount": float(amount),
                        "nonce": p["nonce"]})
    return 200, {"success": True, "transaction": p["nonce"], "network": "simulated",
                 "payer": scope}


def state(scope):
    rows = _ledger(scope)
    settled = {r["nonce"] for r in rows if r.get("action") == "settle"}
    auth = {r["nonce"]: float(r["amount"]) for r in rows
            if r.get("ok") and r.get("action") == "authorize" and r.get("nonce")}
    return {"cap": float(_read(os.path.join(_dir(scope), "cap"), "0") or 0),
            "policy": _read(os.path.join(_dir(scope), "policy"), "cumulative"),
            "committed": round(sum(auth.values()), 2),
            "captured": round(sum(v for k, v in auth.items() if k in settled), 2),
            "authorizations": len(auth), "settled": len(settled),
            "requests": sum(1 for r in rows if r.get("action") == "authorize"),
            "declined": sum(1 for r in rows
                            if r.get("action") == "authorize" and not r.get("ok"))}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        if code == 402:
            self.send_header("WWW-Authenticate", "X402 realm=\"simulated\"")
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad_json"})
        try:
            if self.path == "/pay":
                return self._send(*pay(req["scope"], req["payTo"], req["amount"],
                                       req.get("resource", "")))
            if self.path == "/verify":
                return self._send(*verify(req["payment"], req["payTo"],
                                          req["amount"]))
            if self.path == "/settle":
                return self._send(*settle(req["payment"], req["payTo"],
                                          req["amount"]))
            if self.path == "/init":
                init(req["scope"], req["cap"], policy=req.get("policy", "cumulative"))
                return self._send(200, {"ok": True})
        except KeyError as e:
            return self._send(400, {"error": f"missing field {e}"})
        self._send(404, {"error": "no_such_endpoint"})

    def do_GET(self):
        if self.path.startswith("/state/"):
            return self._send(200, state(self.path.split("/state/", 1)[1]))
        self._send(404, {"error": "no_such_endpoint"})


def serve(port):
    os.makedirs(STATE, exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8402)
