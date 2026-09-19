"""Minimal JSON-RPC client on top of urllib, with batching."""

import json
import urllib.request


class RpcError(Exception):
    pass


class Rpc:
    def __init__(self, url: str, timeout: float = 20.0):
        self.url = url
        self.timeout = timeout
        self._id = 0

    def _post(self, payload):
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"content-type": "application/json", "user-agent": "lpval/0.1"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def request(self, method: str, params: list):
        self._id += 1
        out = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        if "error" in out:
            raise RpcError(f"{method}: {out['error']}")
        return out["result"]

    def batch(self, reqs):
        """reqs: list of (method, params). Returns results in order; a failed item is None."""
        if not reqs:
            return []
        payload = []
        for method, params in reqs:
            self._id += 1
            payload.append({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        try:
            out = self._post(payload)
            if not isinstance(out, list):
                raise RpcError("batch not supported")
        except Exception:
            # Fallback: sequential calls.
            results = []
            for method, params in reqs:
                try:
                    results.append(self.request(method, params))
                except Exception:
                    results.append(None)
            return results
        by_id = {item.get("id"): item for item in out}
        return [by_id.get(p["id"], {}).get("result") for p in payload]

    def eth_calls(self, calls, block="latest"):
        """calls: list of (to, data_hex). Returns list of bytes (or None on revert/error)."""
        tag = block if isinstance(block, str) else hex(block)
        raw = self.batch([("eth_call", [{"to": to, "data": data}, tag]) for to, data in calls])
        return [bytes.fromhex(r[2:]) if isinstance(r, str) and r.startswith("0x") else None for r in raw]

    def block_number(self) -> int:
        return int(self.request("eth_blockNumber", []), 16)

    def block_timestamp(self, number: int) -> int:
        blk = self.request("eth_getBlockByNumber", [hex(number), False])
        if not blk:
            raise RpcError(f"block {number} unavailable")
        return int(blk["timestamp"], 16)
