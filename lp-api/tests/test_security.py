"""Regression tests for the findings of the security review. Each one fails on the old code."""

import base64
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "landing"))

from lpval import secp256k1  # noqa: E402
from lpval.paywall import Paywall, payment_message  # noqa: E402
from lpval.rpc import REVERTED, Rpc, UpstreamError  # noqa: E402

CHAIN = 4663
PAY_TO = "0x00000000000000000000000000000000000000ab"
ROUTE = "/v1/position/1"
# A throwaway key, used only to sign test messages.
KEY = 0x59C6995E998F97A5A0044966F0945389DC9E86DAE88C7A8412F4603B6B78690D


class FakeRpc:
    """Stands in for the chain. Every field the paywall reads can be bent from a test."""

    def __init__(self, **over):
        self.tx = {
            "to": PAY_TO,
            "from": _addr(KEY),
            "value": hex(10**12),
        }
        self.receipt = {"status": "0x1", "blockNumber": hex(1000)}
        self.head = hex(1010)
        self.__dict__.update(over)

    def batch(self, reqs):
        return [self.tx, self.receipt, self.head]


def _addr(priv: int) -> str:
    point = secp256k1._mul((secp256k1.GX, secp256k1.GY), priv)
    raw = point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big")
    from lpval.keccak import keccak256

    return "0x" + keccak256(raw)[12:].hex()


def _sign(priv: int, msg_hash: bytes) -> str:
    """Deterministic ECDSA (RFC 6979 would be nicer; a counter is enough for a test)."""
    import hashlib

    z = int.from_bytes(msg_hash, "big")
    for k in range(1, 1000):
        k = int.from_bytes(hashlib.sha256(msg_hash + k.to_bytes(4, "big")).digest(), "big") % secp256k1.N
        if k == 0:
            continue
        point = secp256k1._mul((secp256k1.GX, secp256k1.GY), k)
        r = point[0] % secp256k1.N
        if r == 0:
            continue
        s = (pow(k, secp256k1.N - 2, secp256k1.N) * (z + r * priv)) % secp256k1.N
        if s == 0:
            continue
        v = point[1] & 1
        if s > secp256k1.N // 2:
            s, v = secp256k1.N - s, v ^ 1
        return "0x" + r.to_bytes(32, "big").hex() + s.to_bytes(32, "big").hex() + bytes([v + 27]).hex()
    raise AssertionError("no signature found")


def _paywall(rpc=None, **env):
    tmp = tempfile.mkdtemp()
    os.environ["LPVAL_PAY_TO"] = PAY_TO
    os.environ["LPVAL_DB"] = os.path.join(tmp, "p.sqlite")
    os.environ["LPVAL_PRICE_WEI"] = "1000000000000"
    os.environ.update(env)
    return Paywall(rpc or FakeRpc(), CHAIN)


def _nonce(pw, route=ROUTE):
    return pw.challenge(route)["accepts"][0]["extra"]["nonce"]


def _proof(pw, tx_hash, priv=KEY, route=ROUTE, nonce=None):
    nonce = nonce or _nonce(pw, route)
    msg = payment_message(tx_hash, route, nonce, CHAIN, PAY_TO)
    return {
        "scheme": "onchain-tx",
        "txHash": tx_hash,
        "payer": _addr(priv),
        "nonce": nonce,
        "signature": _sign(priv, secp256k1.personal_hash(msg)),
    }


TX = "0x" + "ab" * 32


class SignatureTest(unittest.TestCase):
    def test_recover_roundtrip(self):
        h = secp256k1.personal_hash("hello")
        self.assertEqual(secp256k1.recover(h, bytes.fromhex(_sign(KEY, h)[2:])).lower(), _addr(KEY).lower())

    def test_rejects_high_s(self):
        h = secp256k1.personal_hash("hello")
        sig = bytearray(bytes.fromhex(_sign(KEY, h)[2:]))
        sig[32:64] = (secp256k1.N - int.from_bytes(sig[32:64], "big")).to_bytes(32, "big")
        with self.assertRaises(secp256k1.BadSignature):
            secp256k1.recover(h, bytes(sig))


class PaywallTest(unittest.TestCase):
    def test_happy_path(self):
        pw = _paywall()
        ok, reason, receipt = pw.verify(_proof(pw, TX), ROUTE)
        self.assertTrue(ok, reason)
        self.assertEqual(receipt["payer"], _addr(KEY).lower())

    def test_hash_alone_is_not_enough(self):
        """The old bug: whoever saw the hash on chain could spend somebody else's payment."""
        pw = _paywall()
        proof, err = Paywall.parse_proof({"X-Payment-Tx": TX})
        self.assertIsNone(proof)
        self.assertIsNone(err)  # no proof at all, so a plain 402 rather than an accepted payment

    def test_signature_from_another_account_is_rejected(self):
        pw = _paywall()
        other = KEY + 1
        proof = _proof(pw, TX, priv=other)
        proof["payer"] = _addr(KEY)  # claim to be the real payer
        ok, reason, _ = pw.verify(proof, ROUTE)
        self.assertFalse(ok)
        self.assertIn("not produced by the declared payer", reason)

    def test_proof_for_another_route_is_rejected(self):
        pw = _paywall()
        proof = _proof(pw, TX, route="/v1/position/999")
        ok, reason, _ = pw.verify(proof, ROUTE)
        self.assertFalse(ok)

    def test_replay_is_rejected(self):
        pw = _paywall()
        self.assertTrue(pw.verify(_proof(pw, TX), ROUTE)[0])
        ok, reason, _ = pw.verify(_proof(pw, TX), ROUTE)
        self.assertFalse(ok)
        self.assertEqual(reason, "payment already used")

    def test_release_lets_a_failed_request_be_retried_once_only(self):
        pw = _paywall()
        proof = _proof(pw, TX)
        self.assertTrue(pw.verify(proof, ROUTE)[0])
        self.assertTrue(pw.release(TX, proof["payer"], ROUTE))
        self.assertTrue(pw.verify(_proof(pw, TX), ROUTE)[0])
        # A second refund would make the payment a tap for unlimited free work.
        self.assertFalse(pw.release(TX, proof["payer"], ROUTE))

    def test_release_refuses_a_stranger_and_another_route(self):
        pw = _paywall()
        proof = _proof(pw, TX)
        self.assertTrue(pw.verify(proof, ROUTE)[0])
        self.assertFalse(pw.release(TX, "0x" + "11" * 20, ROUTE))
        self.assertFalse(pw.release(TX, proof["payer"], "/v1/position/999"))

    def test_a_trailing_newline_cannot_split_the_ledger(self):
        pw = _paywall()
        self.assertTrue(pw.verify(_proof(pw, TX), ROUTE)[0])
        ok, reason, _ = pw.verify(_proof(pw, TX + chr(10)), ROUTE)
        self.assertFalse(ok)
        self.assertIn("malformed", reason)

    def test_a_nonce_for_another_route_is_refused(self):
        pw = _paywall()
        other = pw.challenge("/v1/position/999")["accepts"][0]["extra"]["nonce"]
        ok, reason, _ = pw.verify(_proof(pw, TX, nonce=other), ROUTE)
        self.assertFalse(ok)
        self.assertIn("nonce", reason)

    def test_zero_confirmations_is_rejected(self):
        pw = _paywall(FakeRpc(head=hex(1000)))
        ok, reason, _ = pw.verify(_proof(pw, TX), ROUTE)
        self.assertFalse(ok)
        self.assertIn("confirmations", reason)

    def test_missing_head_fails_closed(self):
        pw = _paywall(FakeRpc(head=None))
        ok, reason, _ = pw.verify(_proof(pw, TX), ROUTE)
        self.assertFalse(ok)
        self.assertIn("chain head", reason)

    def test_unreachable_chain_does_not_accept(self):
        class Dead:
            def batch(self, reqs):
                raise UpstreamError("down")

        pw = _paywall(Dead())
        ok, reason, _ = pw.verify(_proof(pw, TX), ROUTE)
        self.assertFalse(ok)

    def test_malformed_rpc_shapes_do_not_crash(self):
        for over in [{"tx": "a string"}, {"receipt": {}}, {"tx": {"to": PAY_TO, "value": 12}}, {"head": "zz"}]:
            pw = _paywall(FakeRpc(**over))
            ok, _, _ = pw.verify(_proof(pw, TX), ROUTE)
            self.assertFalse(ok, over)

    def test_garbage_proofs_are_rejected_not_crashes(self):
        for raw in [b"[]", b"1", b"null", b"true", b'{"scheme":"onchain-tx","txHash":1}', b"not-base64"]:
            header = base64.b64encode(raw).decode() if raw != b"not-base64" else "!!!"
            proof, err = Paywall.parse_proof({"PAYMENT-SIGNATURE": header})
            self.assertIsNone(proof)
            self.assertIsInstance(err, str)

    def test_nonce_cannot_be_invented(self):
        pw = _paywall()
        proof = _proof(pw, TX, nonce="0" * 32)
        ok, reason, _ = pw.verify(proof, ROUTE)
        self.assertFalse(ok)
        self.assertIn("nonce", reason)


class RpcTest(unittest.TestCase):
    def test_refuses_plain_http(self):
        with self.assertRaises(ValueError):
            Rpc("http://evil.example")

    def test_reverted_is_not_the_same_as_unreachable(self):
        self.assertIsNot(REVERTED, None)


class WaitlistTest(unittest.TestCase):
    def setUp(self):
        from api import waitlist

        self.waitlist = waitlist
        os.environ["WAITLIST_FILE"] = os.path.join(tempfile.mkdtemp(), "w.jsonl")
        os.environ.pop("WAITLIST_WEBHOOK_URL", None)
        os.environ.pop("VERCEL", None)

    def test_negative_content_length_is_refused(self):
        self.assertIsNone(self.waitlist.read_length("-1"))
        self.assertIsNone(self.waitlist.read_length("abc"))
        self.assertIsNone(self.waitlist.read_length(str(self.waitlist.MAX_BODY + 1)))
        self.assertEqual(self.waitlist.read_length("10"), 10)

    def test_type_confusion_does_not_crash(self):
        for body in [b'{"email":"a@b.co","role":[]}', b'{"email":"a@b.co","source":{}}']:
            status, _ = self.waitlist.process(body)
            self.assertEqual(status, 200)

    def test_no_enumeration_oracle(self):
        first = self.waitlist.process(b'{"email":"a@b.co"}')
        second = self.waitlist.process(b'{"email":"a@b.co"}')
        self.assertEqual(first, second)
        self.assertNotIn("duplicate", json.dumps(second[1]))

    def test_chat_injection_is_stripped(self):
        cleaned = self.waitlist._safe("x`[click](https://evil.tld)`y@z.co")
        for ch in "`[]()":
            self.assertNotIn(ch, cleaned)


class EnvelopeTest(unittest.TestCase):
    """The 402 body follows x402 version 2, so a standard client understands the shape even though
    our policy inside it is stricter than the usual confirmed-transaction proof."""

    def test_shape(self):
        pw = _paywall()
        env = pw.challenge(ROUTE, "https://api.example")
        self.assertEqual(env["x402Version"], 2)
        accept = env["accepts"][0]
        self.assertEqual(accept["network"], f"eip155:{CHAIN}")
        self.assertEqual(accept["payTo"], PAY_TO)
        self.assertEqual(accept["asset"], "0x" + "0" * 40)
        self.assertEqual(accept["amount"], "1000000000000")
        self.assertEqual(env["resource"]["url"], "https://api.example" + ROUTE)
        self.assertEqual(env["resource"]["path"], ROUTE)

    def test_signature_requirement_is_advertised(self):
        pw = _paywall()
        extra = pw.challenge(ROUTE)["accepts"][0]["extra"]
        self.assertIn("payer-signature", extra["proof"])
        self.assertEqual(len(extra["nonce"]), 32)
        self.assertIn("nonce: " + extra["nonce"], extra["signThis"])

    def test_the_host_header_is_never_signed(self):
        pw = _paywall()
        env = pw.challenge(ROUTE, "https://attacker.example")
        self.assertNotIn("attacker.example", env["accepts"][0]["extra"]["signThis"])

    def test_every_header_spelling_is_accepted(self):
        body = json.dumps({"scheme": "onchain-tx", "txHash": TX, "payer": PAY_TO, "nonce": "a" * 32,
                           "signature": "0x" + "11" * 65})
        packed = base64.b64encode(body.encode()).decode()
        for headers in (
            {"PAYMENT-SIGNATURE": packed},
            {"X402-PAYMENT": packed},
            {"Authorization": "x402 " + packed},
            {"PAYMENT-SIGNATURE": body},  # raw JSON, as some clients send
        ):
            proof, err = Paywall.parse_proof(headers)
            self.assertIsNone(err, headers)
            self.assertEqual(proof["txHash"], TX)



class ConcurrencyTest(unittest.TestCase):
    """Regressions for the findings of the concurrency review."""

    def setUp(self):
        from lpval import server

        self.server = server
        server._cache.clear()
        server._inflight.clear()

    def test_a_failed_leader_does_not_serve_a_stale_entry(self):
        import threading, time as t

        key = ("stale", 0)
        self.server._cache[key] = (t.time() - 3600, {"old": True})
        seen = []

        def build():
            t.sleep(0.2)
            raise RuntimeError("upstream down")

        def run():
            try:
                seen.append(("ok", self.server._cached(key, build)))
            except Exception as exc:
                seen.append(("err", type(exc).__name__))

        threads = [threading.Thread(target=run) for _ in range(6)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(10)
        self.assertTrue(all(kind == "err" for kind, _ in seen), seen)

    def test_a_failed_leader_does_not_cause_a_stampede(self):
        import threading, time as t

        builds = []
        lock = threading.Lock()

        def build():
            with lock:
                builds.append(1)
            t.sleep(0.2)
            raise RuntimeError("upstream down")

        def run():
            try:
                self.server._cached(("boom", 0), build)
            except Exception:
                pass

        threads = [threading.Thread(target=run) for _ in range(12)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(10)
        self.assertEqual(len(builds), 1, f"{len(builds)} builds for 12 concurrent requests")

    def test_the_leader_is_deduplicated_on_the_happy_path(self):
        import threading, time as t

        builds = []

        def build():
            builds.append(1)
            t.sleep(0.2)
            return {"value": 1}

        out = []
        threads = [threading.Thread(target=lambda: out.append(self.server._cached(("ok", 0), build))) for _ in range(12)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(10)
        self.assertEqual(len(builds), 1)
        self.assertEqual(len(out), 12)
        self.assertTrue(all(o == {"value": 1} for o in out))


class RpcErrorShapeTest(unittest.TestCase):
    def test_a_revert_and_an_unreachable_node_are_different(self):
        from lpval.rpc import REVERTED, UNAVAILABLE, Rpc

        revert = {"error": {"code": 3, "message": "execution reverted"}}
        reverted_by_text = {"error": {"code": -32000, "message": "execution reverted: bad token"}}
        rate_limited = {"error": {"code": -32005, "message": "rate limit exceeded"}}
        self.assertIs(Rpc._item_result(revert), REVERTED)
        self.assertIs(Rpc._item_result(reverted_by_text), REVERTED)
        self.assertIs(Rpc._item_result(rate_limited), UNAVAILABLE)
        self.assertIs(Rpc._item_result(None), UNAVAILABLE)
        self.assertEqual(Rpc._item_result({"result": "0x01"}), "0x01")


class ChatInjectionTest(unittest.TestCase):
    def test_a_bare_url_cannot_render_as_a_link(self):
        from api import waitlist

        cleaned = waitlist._safe("https://evil.example/?x=y@z.co")
        for ch in ":/?=&@":
            self.assertNotIn(ch, cleaned)

if __name__ == "__main__":
    unittest.main()
