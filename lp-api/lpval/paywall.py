"""Pay-per-request gate: HTTP 402 challenge, settled by a confirmed on-chain ETH transfer.

Flow:
  1. Client calls a paid route with no payment header. Server answers 402 with payTo / amountWei / chainId.
  2. Client sends that amount of ETH to payTo on Robinhood Chain.
  3. Client retries with header `X-Payment-Tx: 0x<txhash>`.
  4. Server checks the tx (recipient, value, success, recent) and that the hash was never used before.

Disabled unless LPVAL_PAY_TO is set, so the prototype runs free by default.
"""

import base64
import json
import os
import sqlite3
import threading

from .rpc import Rpc

MAX_AGE_BLOCKS = 36_000  # about one hour of 100 ms blocks


class Paywall:
    def __init__(self, rpc: Rpc, chain_id: int):
        self.rpc = rpc
        self.chain_id = chain_id
        self.pay_to = (os.environ.get("LPVAL_PAY_TO") or "").lower()
        self.price_wei = int(os.environ.get("LPVAL_PRICE_WEI", "1000000000000"))  # 0.000001 ETH
        self.enabled = bool(self.pay_to)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(os.environ.get("LPVAL_DB", "lpval_payments.sqlite"), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS used (tx TEXT PRIMARY KEY, payer TEXT, route TEXT)")
        self._db.commit()

    def challenge(self, route: str) -> dict:
        return {
            "error": "payment_required",
            "scheme": "onchain-tx",
            "chainId": self.chain_id,
            "caip2": f"eip155:{self.chain_id}",
            "asset": "ETH",
            "payTo": self.pay_to,
            "amountWei": str(self.price_wei),
            "resource": route,
            "instructions": "Send amountWei of ETH to payTo, then retry with header PAYMENT-SIGNATURE: "
            'base64({"scheme":"onchain-tx","txHash":"0x..","payer":"0x.."}) or X-Payment-Tx: <tx hash>. '
            "One payment buys one request.",
        }

    @staticmethod
    def parse_proof(headers):
        """Accepts the Olanas-style proof or the bare-hash shortcut. Returns (tx_hash, payer, error).

        PAYMENT-SIGNATURE: base64(JSON {"scheme": "onchain-tx", "txHash": "0x..", "payer": "0x.."})
        X-Payment-Tx:      0x<txhash>
        """
        sig = headers.get("PAYMENT-SIGNATURE")
        if sig:
            try:
                proof = json.loads(base64.b64decode(sig + "=" * (-len(sig) % 4)))
            except Exception:
                return None, None, "PAYMENT-SIGNATURE is not base64-encoded JSON"
            if proof.get("scheme") != "onchain-tx":
                return None, None, "unsupported scheme, expected onchain-tx"
            return proof.get("txHash"), proof.get("payer"), None
        return headers.get("X-Payment-Tx"), None, None

    @staticmethod
    def encode(obj: dict) -> str:
        return base64.b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode()

    def verify(self, tx_hash: str, route: str, payer: str = None):
        """Returns (ok, reason, receipt). Stricter than Olanas: one payment buys exactly one request."""
        ok, reason, tx = self._verify(tx_hash, route, payer)
        if not ok:
            return False, reason, None
        receipt = {
            "success": True,
            "scheme": "onchain-tx",
            "network": f"eip155:{self.chain_id}",
            "transaction": tx_hash.lower(),
            "payer": tx.get("from"),
            "payTo": self.pay_to,
            "amountWei": str(int(tx.get("value", "0x0"), 16)),
            "resource": route,
        }
        return True, "ok", receipt

    def _verify(self, tx_hash: str, route: str, payer: str = None):
        tx_hash = (tx_hash or "").lower()
        if not (tx_hash.startswith("0x") and len(tx_hash) == 66):
            return False, "malformed tx hash", None
        res = self.rpc.batch(
            [
                ("eth_getTransactionByHash", [tx_hash]),
                ("eth_getTransactionReceipt", [tx_hash]),
                ("eth_blockNumber", []),
            ]
        )
        tx, receipt, head = res
        if not tx or not receipt:
            return False, "transaction not found or not yet confirmed", None
        if receipt.get("status") != "0x1":
            return False, "transaction failed", None
        if (tx.get("to") or "").lower() != self.pay_to:
            return False, "wrong recipient", None
        if payer and (tx.get("from") or "").lower() != payer.lower():
            return False, "payer does not match the transaction sender", None
        if int(tx.get("value", "0x0"), 16) < self.price_wei:
            return False, "amount too low", None
        if head and int(head, 16) - int(receipt["blockNumber"], 16) > MAX_AGE_BLOCKS:
            return False, "payment too old", None
        with self._lock:
            try:
                self._db.execute("INSERT INTO used (tx, payer, route) VALUES (?, ?, ?)", (tx_hash, tx.get("from"), route))
                self._db.commit()
            except sqlite3.IntegrityError:
                return False, "payment already used", None
        return True, "ok", tx
