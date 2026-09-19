"""Pay-per-request gate: HTTP 402, settled by a confirmed on-chain transfer plus a signature.

Why the signature. A transaction hash is public the moment it lands, so if the hash alone bought a
response, anyone watching the chain could spend a customer's payment before the customer redeemed
it — and any unrelated transfer that happened to reach our address would be a free request. The
payer therefore signs a message naming the transaction, the resource and a nonce the server issued,
and we only accept the proof if the recovered signer is the account that actually sent the money.

Flow:
  1. Client calls a paid route with no proof. Server answers 402 with payTo, amountWei and a nonce.
  2. Client sends the ETH, then signs `payment_message(...)` with the sending account.
  3. Client retries with `PAYMENT-SIGNATURE: base64({scheme, txHash, payer, nonce, signature})`.
  4. Server checks the transfer, the signature, the nonce and that the hash was never spent.

Disabled unless LPVAL_PAY_TO is set, so the prototype runs free by default.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time

from .rpc import Rpc, UpstreamError
from .secp256k1 import BadSignature, personal_hash, recover

MIN_CONFIRMATIONS = int(os.environ.get("LPVAL_MIN_CONFIRMATIONS", "3"))
MAX_AGE_BLOCKS = 36_000  # about one hour of 100 ms blocks
NONCE_TTL = 900  # seconds a challenge stays redeemable
# \Z, not $: in Python `$` also matches before a trailing newline, which would make "0xab..ab" and
# "0xab..ab\n" two distinct keys in the spend ledger, and therefore one payment redeemable twice.
HASH_RE = re.compile(r"^0x[0-9a-f]{64}\Z")
ADDR_RE = re.compile(r"^0x[0-9a-f]{40}\Z")
NATIVE_ASSET = "0x" + "0" * 40  # how x402 names a chain's own coin rather than a token


def payment_message(tx_hash: str, resource: str, nonce: str, chain_id: int, pay_to: str) -> str:
    """The exact text the payer signs. Naming the resource and the nonce is what stops a proof for
    one request being replayed against another."""
    return (
        "tenure payment\n"
        f"chain: {chain_id}\n"
        f"to: {pay_to}\n"
        f"tx: {tx_hash}\n"
        f"resource: {resource}\n"
        f"nonce: {nonce}"
    )


class Paywall:
    def __init__(self, rpc: Rpc, chain_id: int):
        self.rpc = rpc
        self.chain_id = chain_id
        self.pay_to = (os.environ.get("LPVAL_PAY_TO") or "").lower()
        self.price_wei = int(os.environ.get("LPVAL_PRICE_WEI", "1000000000000"))  # 0.000001 ETH
        self.enabled = bool(self.pay_to)
        if self.enabled and not ADDR_RE.match(self.pay_to):
            raise ValueError("LPVAL_PAY_TO is not an address")
        self._lock = threading.Lock()
        self._db = sqlite3.connect(os.environ.get("LPVAL_DB", "lpval_payments.sqlite"), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        # `ts` exists so spent payments can be pruned once they are past redeeming.
        self._db.execute("CREATE TABLE IF NOT EXISTS used (tx TEXT PRIMARY KEY, payer TEXT, route TEXT, ts INTEGER)")
        # A ledger written before `ts` existed must still open, or the service will not start at all
        # on any machine that has already taken a payment.
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(used)")}
        if "ts" not in columns:
            self._db.execute("ALTER TABLE used ADD COLUMN ts INTEGER")
            self._db.execute("UPDATE used SET ts = ? WHERE ts IS NULL", (int(time.time()),))
        # A payment may be handed back once when we fail to deliver. Recording that stops the refund
        # from being a free-work tap: pay once, fail on purpose, retry, forever.
        self._db.execute("CREATE TABLE IF NOT EXISTS refunded (tx TEXT PRIMARY KEY, ts INTEGER)")
        self._db.execute("CREATE INDEX IF NOT EXISTS used_ts ON used (ts)")
        self._db.commit()
        self._last_prune = 0.0
        # Keyed, so a nonce can be verified by recomputation rather than stored. Set it in the
        # environment to keep challenges valid across a restart or across several workers.
        key = os.environ.get("LPVAL_NONCE_KEY")
        self._nonce_key = key.encode() if key else secrets.token_bytes(32)

    # ------------------------------------------------------------------ challenge

    def _mint_nonce(self, route: str) -> str:
        """A nonce nobody but this server can produce, and that costs nothing to issue.

        It used to be a row in SQLite, which made every anonymous request an unauthenticated write:
        a few hundred GETs a second filled the table with challenges nobody would ever redeem. It is
        now a timestamp plus a keyed digest over the route, so it is verified by recomputation.
        Single use is not this value's job; the spend ledger already makes each payment single use.
        """
        stamp = format(int(time.time()), "x").rjust(8, "0")
        mac = hmac.new(self._nonce_key, f"{stamp}|{route}".encode(), hashlib.sha256).hexdigest()[:24]
        return stamp + mac

    def _nonce_valid(self, nonce: str, route: str) -> bool:
        if not isinstance(nonce, str) or len(nonce) != 32:
            return False
        stamp, mac = nonce[:8], nonce[8:]
        try:
            issued = int(stamp, 16)
        except ValueError:
            return False
        if not 0 <= time.time() - issued <= NONCE_TTL:
            return False
        expect = hmac.new(self._nonce_key, f"{stamp}|{route}".encode(), hashlib.sha256).hexdigest()[:24]
        return hmac.compare_digest(mac, expect)

    def challenge(self, route: str, base_url: str = "") -> dict:
        """An x402 version 2 envelope, so any client built for the standard understands the shape.

        The policy inside it is stricter than the usual `confirmed-transaction` proof: we also want
        the payer's signature, because a transaction hash is public the moment it is mined and would
        otherwise be a bearer token. A client that ignores `extra` fails closed, which is the point.
        """
        nonce = self._mint_nonce(route)
        self._maybe_prune()
        return {
            "x402Version": 2,
            "error": "Payment required",
            "accepts": [
                {
                    "scheme": "onchain-tx",
                    "network": f"eip155:{self.chain_id}",
                    "amount": str(self.price_wei),
                    "asset": NATIVE_ASSET,
                    "payTo": self.pay_to,
                    "maxTimeoutSeconds": NONCE_TTL,
                    "extra": {
                        "name": "ETH",
                        "version": "1",
                        "proof": "confirmed-transaction+payer-signature",
                        "minConfirmations": MIN_CONFIRMATIONS,
                        "nonce": nonce,
                        # Signed over the path, never over the Host header, which a client controls.
                        "signThis": payment_message("<txHash>", route, nonce, self.chain_id, self.pay_to),
                    },
                }
            ],
            "resource": {
                "url": f"{base_url}{route}" if base_url else route,
                "path": route,
                "mimeType": "application/json",
                "description": f"Paid request costing {self.price_wei} wei on chain {self.chain_id}",
            },
            "instructions": (
                "Send amount wei of ETH to payTo, sign the accepts[0].extra.signThis text with the "
                "sending account (personal_sign, with <txHash> replaced by the real hash), then retry "
                "with PAYMENT-SIGNATURE (or X402-PAYMENT, or Authorization: x402 ...) carrying "
                '{"scheme":"onchain-tx","txHash":"0x..","payer":"0x..","nonce":"..","signature":"0x.."} '
                "as raw JSON or base64."
            ),
        }

    # ------------------------------------------------------------------ proof parsing

    @staticmethod
    def parse_proof(headers):
        """Returns (proof, error). `proof` is a dict of strings, never anything else.

        Three header spellings are accepted because three are in use in the wild, and the payload
        may be raw JSON or base64. Being liberal about the envelope costs nothing; the strictness
        that matters is in what the fields have to prove.
        """
        sig = headers.get("PAYMENT-SIGNATURE") or headers.get("X402-PAYMENT")
        if not sig:
            auth = headers.get("Authorization") or ""
            if auth.lower().startswith("x402 "):
                sig = auth[5:].strip()
        if not sig:
            return None, None
        try:
            if sig.lstrip().startswith("{"):
                proof = json.loads(sig)
            else:
                proof = json.loads(base64.b64decode(sig + "=" * (-len(sig) % 4), validate=False))
        except Exception:
            return None, "the payment proof is neither JSON nor base64-encoded JSON"
        if not isinstance(proof, dict):
            return None, "the proof must be a JSON object"
        if proof.get("scheme") != "onchain-tx":
            return None, "unsupported scheme, expected onchain-tx"
        out = {}
        for field in ("txHash", "payer", "nonce", "signature"):
            value = proof.get(field)
            if not isinstance(value, str):
                return None, f"missing or malformed field: {field}"
            out[field] = value
        return out, None

    @staticmethod
    def encode(obj: dict) -> str:
        return base64.b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode()

    # ------------------------------------------------------------------ verification

    def verify(self, proof: dict, route: str):
        """Returns (ok, reason, receipt). On failure nothing is consumed and the client may retry."""
        tx_hash = proof["txHash"].lower()
        payer = proof["payer"].lower()
        if not HASH_RE.match(tx_hash):
            return False, "malformed transaction hash", None
        if not ADDR_RE.match(payer):
            return False, "malformed payer address", None

        # Cheap checks before any upstream call, so a spray of invalid proofs costs us nothing.
        if self._is_spent(tx_hash):
            return False, "payment already used", None
        if not self._nonce_valid(proof["nonce"], route):
            return False, "unknown or expired nonce, request a new challenge", None
        try:
            signer = recover(
                personal_hash(payment_message(tx_hash, route, proof["nonce"], self.chain_id, self.pay_to)),
                bytes.fromhex(proof["signature"][2:] if proof["signature"].startswith("0x") else proof["signature"]),
            )
        except (BadSignature, ValueError):
            return False, "signature does not verify", None
        if signer.lower() != payer:
            return False, "signature was not produced by the declared payer", None

        ok, reason, tx = self._check_transfer(tx_hash, payer)
        if not ok:
            return False, reason, None
        if not self._spend(tx_hash, payer, route):
            return False, "payment already used", None
        return True, "ok", {
            "success": True,
            "scheme": "onchain-tx",
            "network": f"eip155:{self.chain_id}",
            "transaction": tx_hash,
            "payer": payer,
            "payTo": self.pay_to,
            "amountWei": str(int(tx["value"], 16)),
            "resource": route,
        }

    def _check_transfer(self, tx_hash: str, payer: str):
        """Everything the chain has to agree with before a payment counts."""
        try:
            tx, receipt, head = self.rpc.batch(
                [
                    ("eth_getTransactionByHash", [tx_hash]),
                    ("eth_getTransactionReceipt", [tx_hash]),
                    ("eth_blockNumber", []),
                ]
            )
        except UpstreamError:
            return False, "cannot reach the chain right now", None
        if not isinstance(tx, dict) or not isinstance(receipt, dict):
            return False, "transaction not found or not yet confirmed", None
        # Fail closed: without the head we cannot judge age or depth at all.
        if not isinstance(head, str):
            return False, "cannot determine the chain head", None
        try:
            value = int(tx["value"], 16)
            mined_in = int(receipt["blockNumber"], 16)
            tip = int(head, 16)
        except (KeyError, TypeError, ValueError):
            return False, "malformed response from the chain", None

        if receipt.get("status") != "0x1":
            return False, "transaction failed", None
        if not isinstance(tx.get("to"), str) or tx["to"].lower() != self.pay_to:
            return False, "wrong recipient", None
        if not isinstance(tx.get("from"), str) or tx["from"].lower() != payer:
            return False, "the declared payer did not send this transaction", None
        if value < self.price_wei:
            return False, "amount too low", None
        if tip - mined_in < MIN_CONFIRMATIONS:
            return False, f"not enough confirmations yet, need {MIN_CONFIRMATIONS}", None
        if tip - mined_in > MAX_AGE_BLOCKS:
            return False, "payment too old", None
        return True, "ok", tx

    # ------------------------------------------------------------------ ledger

    def _is_spent(self, tx_hash: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM used WHERE tx=?", (tx_hash,)).fetchone() is not None

    def _spend(self, tx_hash: str, payer: str, route: str) -> bool:
        """Atomically claims the payment. False means somebody else got there first."""
        with self._lock:
            try:
                self._db.execute("INSERT INTO used VALUES (?,?,?,?)", (tx_hash, payer, route, int(time.time())))
                self._db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def release(self, tx_hash: str, payer: str, route: str) -> bool:
        """Hand a payment back after a failure on our side, at most once, and only to the request
        that claimed it. Without both limits this is a tap for unlimited free work, and one refactor
        away from letting anyone free somebody else's payment."""
        tx_hash, payer = tx_hash.lower(), payer.lower()
        with self._lock:
            if self._db.execute("SELECT 1 FROM refunded WHERE tx=?", (tx_hash,)).fetchone():
                return False
            row = self._db.execute("SELECT payer, route FROM used WHERE tx=?", (tx_hash,)).fetchone()
            if not row or row[0] != payer or row[1] != route:
                return False
            self._db.execute("DELETE FROM used WHERE tx=?", (tx_hash,))
            self._db.execute("INSERT OR IGNORE INTO refunded VALUES (?,?)", (tx_hash, int(time.time())))
            self._db.commit()
            return True



    def _maybe_prune(self) -> None:
        """Spent payments and stale challenges are dead weight once they can no longer be redeemed."""
        now = time.time()
        if now - self._last_prune < 3600:
            return
        self._last_prune = now
        cutoff = int(now) - 2 * 3600
        with self._lock:
            self._db.execute("DELETE FROM used WHERE ts < ?", (cutoff,))
            self._db.execute("DELETE FROM refunded WHERE ts < ?", (cutoff,))
            self._db.commit()
