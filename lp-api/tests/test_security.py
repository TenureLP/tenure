"""Regression tests for the findings of the security review. Each one fails on the old code."""

import base64
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "landing"))

from lpval import secp256k1, valuation  # noqa: E402
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

    def test_the_endpoint_never_escapes_in_an_error(self):
        """The API key lives in the RPC url, and a failed fee-rate probe publishes its reason on a
        public route. Nothing upstream promises not to quote the url it was fetching."""
        # Shaped like a provider key, obviously not one, so no secret scanner ever has to decide.
        key = "NOT-A-REAL-KEY-0000000000"
        rpc = Rpc(f"https://node.example/v2/{key}")

        leaky = f"<urlopen error for https://node.example/v2/{key}>"
        self.assertNotIn(key, rpc.scrub(leaky))
        self.assertNotIn(key, rpc.scrub(f"rate limited on key {key}"))
        self.assertIn("the RPC endpoint", rpc.scrub(leaky))
        # Ordinary text is left alone.
        self.assertEqual(rpc.scrub("HTTP 429"), "HTTP 429")

    def test_scrubbing_does_not_mangle_a_keyless_endpoint(self):
        rpc = Rpc("https://rpc.mainnet.chain.robinhood.com")
        self.assertEqual(rpc.scrub("HTTP 500 from the node"), "HTTP 500 from the node")

    def test_a_key_carried_in_a_header_is_also_scrubbed(self):
        """Providers split on where the secret goes. One puts it in the path, the next wants a
        header, and both end up quoted back in somebody's error message."""
        rpc = Rpc("https://node.example|x-api-key:ORBIT-HEADER-SECRET-0000")
        self.assertNotIn("ORBIT-HEADER-SECRET-0000", rpc.scrub("refused: key ORBIT-HEADER-SECRET-0000"))

    def test_what_may_be_logged_is_hosts_only(self):
        rpc = Rpc("https://a.example/v2/PATHSECRET12345  https://b.example|x-api-key:HEADERSECRET12345")
        said = rpc.describe()
        self.assertEqual(said, "a.example, b.example")
        for secret in ("PATHSECRET12345", "HEADERSECRET12345"):
            self.assertNotIn(secret, said)

    def test_headers_reach_the_endpoint_that_asked_for_them(self):
        rpc = Rpc("https://a.example/v2/K  https://b.example|x-api-key:SECRET-VALUE-123")
        self.assertEqual(rpc.endpoints[0].headers, {})
        self.assertEqual(rpc.endpoints[1].headers, {"x-api-key": "SECRET-VALUE-123"})

    def test_a_malformed_header_is_refused_rather_than_ignored(self):
        # Silently dropping it would mean an endpoint that quietly 401s on every call.
        with self.assertRaises(ValueError):
            Rpc("https://a.example|x-api-key")


class FailoverTest(unittest.TestCase):
    """Several endpoints exist so that one of them being unhappy is not an outage."""

    @staticmethod
    def _rpc(behaviour):
        rpc = Rpc("https://a.example  https://b.example")
        seen = []

        def fake_post_once(payload, endpoint):
            seen.append(endpoint.label)
            return behaviour(endpoint.label, payload)

        rpc._post_once = fake_post_once
        return rpc, seen

    @staticmethod
    def _http_error(code):
        return urllib.error.HTTPError("https://a.example", code, "nope", {}, None)

    def test_a_bad_key_on_one_endpoint_does_not_fail_the_read(self):
        def behaviour(label, payload):
            if label == "a.example":
                raise FailoverTest._http_error(401)
            return {"jsonrpc": "2.0", "id": payload["id"], "result": "0x1237"}

        rpc, seen = self._rpc(behaviour)
        self.assertEqual(rpc.request("eth_chainId", []), "0x1237")
        self.assertEqual(seen, ["a.example", "b.example"])

    def test_an_endpoint_that_refused_us_is_not_asked_again(self):
        """401 says something about our key, not about the weather. Repeating it wastes the budget
        the deadline is there to protect."""

        def behaviour(label, payload):
            raise FailoverTest._http_error(401)

        rpc, seen = self._rpc(behaviour)
        with self.assertRaises(UpstreamError):
            rpc.request("eth_chainId", [])
        self.assertEqual(sorted(seen), ["a.example", "b.example"])

    def test_a_rate_limit_is_worth_asking_about_again(self):
        state = {"n": 0}

        def behaviour(label, payload):
            state["n"] += 1
            if state["n"] < 3:
                raise FailoverTest._http_error(429)
            return {"jsonrpc": "2.0", "id": payload["id"], "result": "0x1"}

        rpc, seen = self._rpc(behaviour)
        self.assertEqual(rpc.request("eth_blockNumber", []), "0x1")
        self.assertEqual(len(seen), 3)

    def test_persist_asks_elsewhere_when_a_node_cannot_serve_the_state(self):
        """The finding that motivated this: the same historical call against one provider succeeded
        nine times in twelve, because it fronts a pool and only some of its nodes keep the state.
        Taking the first refusal as final made the fee rate, and so the rent, a coin toss."""

        def behaviour(label, payload):
            if label == "a.example":
                return [
                    {"id": p["id"], "error": {"code": -32000, "message": "historical state unavailable"}}
                    for p in payload
                ]
            return [{"id": p["id"], "result": "0x" + "11" * 32} for p in payload]

        rpc, seen = self._rpc(behaviour)
        out = rpc.eth_calls([("0xabc", "0xdead")], block=123, persist=True)
        self.assertEqual(out[0], bytes.fromhex("11" * 32))
        self.assertIn("b.example", seen)

    def test_without_persist_one_refusal_is_final(self):
        def behaviour(label, payload):
            return [
                {"id": p["id"], "error": {"code": -32000, "message": "historical state unavailable"}}
                for p in payload
            ]

        rpc, seen = self._rpc(behaviour)
        with self.assertRaises(UpstreamError):
            rpc.eth_calls([("0xabc", "0xdead")], block=123)
        self.assertEqual(seen, ["a.example"])

    def test_a_revert_is_still_not_an_outage(self):
        """The whole point of the client. Failover must not blur it."""

        def behaviour(label, payload):
            return [{"id": p["id"], "error": {"code": 3, "message": "execution reverted"}} for p in payload]

        rpc, seen = self._rpc(behaviour)
        out = rpc.eth_calls([("0xabc", "0xdead")], block="latest")
        self.assertIs(out[0], REVERTED)
        self.assertEqual(seen, ["a.example"])


class QuoteTest(unittest.TestCase):
    """The vault refuses a listing whose price or rent is zero. A quote that cannot produce both is
    not a set of terms anybody can act on, and saying `available` anyway sends a caller to a
    transaction that reverts."""

    @staticmethod
    def _valuation(total, fee_rate):
        return {
            "valueUSDG": {"principal": total, "fees": 0.0, "total": total},
            "position": {"inRange": True, "hasSubscriber": False},
            "feeRate": fee_rate,
        }

    def test_an_empty_position_is_not_quotable(self):
        # A closed position still reads as in range across its full tick span, so eligibility alone
        # would call it fundable at a price of zero.
        q = valuation.quote(self._valuation(0.0, {"available": True, "plausible": True, "feesPerDayUSDG": 1.0}))
        self.assertFalse(q["available"])
        self.assertNotIn("suggestedSalePriceUSDG", q)

    def test_implausible_fees_do_not_produce_a_rentless_quote(self):
        """A fee-growth counter that has wrapped yields absurd fees. It is caught, and the quote
        used to keep saying available with a null rent."""
        q = valuation.quote(
            self._valuation(1000.0, {"available": True, "plausible": False, "feesPerDayUSDG": 4.1e49})
        )
        self.assertFalse(q["available"])
        self.assertEqual(q["marketValueUSDG"], 1000.0)
        self.assertIsNone(q.get("suggestedRentUSDG"))

    def test_a_usable_rate_quotes_both_sides_and_no_spread(self):
        q = valuation.quote(
            self._valuation(1000.0, {"available": True, "plausible": True, "feesPerDayUSDG": 2.0}),
            term_days=7,
            haircut=0.20,
            rent_share=0.5,
        )
        self.assertTrue(q["available"])
        self.assertEqual(q["suggestedSalePriceUSDG"], 800.0)
        # The financier's return comes from the rent, never from a spread on the buyback.
        self.assertEqual(q["suggestedBuybackPriceUSDG"], q["suggestedSalePriceUSDG"])
        self.assertEqual(q["expectedFeesOverTermUSDG"], 14.0)
        self.assertEqual(q["suggestedRentUSDG"], 7.0)


class FeeWindowTest(unittest.TestCase):
    """The fee rate is only as good as the window it was measured over, and the depth of history a
    node serves is not knowable in advance."""

    class _Rpc:
        """Answers historical calls only within `depth` blocks, like a pruning node."""

        HEAD = 1_000_000

        def __init__(self, depth):
            self.depth = depth
            self.asked = []

        def block_number(self):
            return self.HEAD

        def block_timestamp(self, block):
            return block // 10  # 100 ms blocks

        def eth_calls(self, calls, block, persist=False):
            self.asked.append(block)
            if self.HEAD - block > self.depth:
                raise RuntimeError("missing trie node")
            return [b"\x00" * 31 + b"\x07" + b"\x00" * 31 + b"\x09"]

    _POS = {"poolId": "0x" + "ab" * 32, "tickLower": -60, "tickUpper": 60}

    def test_an_archive_node_answers_the_whole_window(self):
        rpc = self._Rpc(depth=10**9)
        source, elapsed, words = valuation._rpc_window(rpc, self._POS, lookback_hours=24.0)
        self.assertEqual(source, "rpc-archive")
        self.assertEqual(elapsed, 24 * 3600)
        self.assertEqual(list(words), [7, 9])

    def test_a_pruning_node_falls_back_to_the_short_window(self):
        rpc = self._Rpc(depth=valuation.SHORT_WINDOW_BLOCKS)
        source, elapsed, _ = valuation._rpc_window(rpc, self._POS, lookback_hours=24.0)
        self.assertEqual(source, "rpc-short-window")
        self.assertEqual(elapsed, valuation.SHORT_WINDOW_BLOCKS // 10)

    def _fee_rate_with(self, snapshot_age, archive_window):
        """Runs the source choice with a snapshot of a given age and an archive read of a given
        width, and reports which one the rate ended up being measured over."""
        from lpval import snapshots

        now = int(time.time())
        position = {
            "poolId": "0x" + "ab" * 32,
            "tickLower": -60,
            "tickUpper": 60,
            "liquidity": 10**18,
            "feeGrowthInside0": 2000,
            "feeGrowthInside1": 2000,
            "token0": {"address": "0x" + "00" * 20, "decimals": 18, "symbol": "X"},
            "token1": {"address": valuation.USDG, "decimals": 6, "symbol": "USDG"},
            "sqrtPriceX96": 2**96,
        }
        originals = (snapshots.oldest_within, snapshots.record, valuation._rpc_window)
        try:
            snapshots.oldest_within = lambda *a, **k: (now - snapshot_age, 1000, 1000) if snapshot_age else None
            snapshots.record = lambda *a, **k: None
            valuation._rpc_window = (
                (lambda *a, **k: ("rpc-archive", archive_window, (500, 500))) if archive_window else (lambda *a, **k: None)
            )
            return valuation._fee_rate(None, position, 1000.0, lookback_hours=24.0)
        finally:
            snapshots.oldest_within, snapshots.record, valuation._rpc_window = originals

    def test_a_narrow_snapshot_does_not_beat_a_wide_archive_read(self):
        """Our own snapshots are only ever as wide as our uptime. Letting any of them win meant a
        service up for fifty minutes quoted a rent off fifty minutes, with a full day of history one
        archive call away. Only visible once it was running."""
        res = self._fee_rate_with(snapshot_age=2880, archive_window=24 * 3600)
        self.assertEqual(res["source"], "rpc-archive")
        self.assertEqual(res["windowSeconds"], 24 * 3600)

    def test_a_snapshot_that_covers_the_window_is_kept(self):
        # Exact, already held, and no round trip: no reason to ask a node for it.
        res = self._fee_rate_with(snapshot_age=23 * 3600, archive_window=24 * 3600)
        self.assertEqual(res["source"], "snapshot")

    def test_a_narrow_snapshot_survives_an_archive_that_answers_nothing(self):
        res = self._fee_rate_with(snapshot_age=2880, archive_window=None)
        self.assertEqual(res["source"], "snapshot")
        self.assertTrue(res["lowConfidence"])

    def test_the_fallback_never_widens_the_window(self):
        """Answering over more history than was asked for answers a different question, and the
        caller prices a deal on the answer."""
        rpc = self._Rpc(depth=0)
        self.assertIsNone(valuation._rpc_window(rpc, self._POS, lookback_hours=0.05))
        widened = [b for b in rpc.asked if self._Rpc.HEAD - b > int(0.05 * 3600 / valuation.BLOCK_SECONDS)]
        self.assertEqual(widened, [])


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

    def test_a_file_on_an_ephemeral_disk_is_not_durable(self):
        """Same rule as the payment ledger: on a platform that replaces containers, the file has to
        sit under a mount the operator declared. A signup collected onto a disk that is about to be
        discarded is worse than one refused, because the page looks like it worked."""
        import server

        for var in ("PORT", "WAITLIST_DATA_DIR", "WAITLIST_FILE"):
            os.environ.pop(var, None)

        os.environ["WAITLIST_FILE"] = "/app/waitlist.jsonl"
        self.assertTrue(server.storage_is_durable(), "no PORT means local, where any path is fine")

        os.environ["PORT"] = "8080"
        self.assertFalse(server.storage_is_durable(), "a container path with no declared volume")

        os.environ["WAITLIST_DATA_DIR"] = "/data"
        self.assertFalse(server.storage_is_durable(), "declared volume, but the file is outside it")

        os.environ["WAITLIST_FILE"] = "/data/waitlist.jsonl"
        self.assertTrue(server.storage_is_durable())

        for var in ("PORT", "WAITLIST_DATA_DIR", "WAITLIST_FILE"):
            os.environ.pop(var, None)

    def test_reader_deduplicates_and_survives_a_half_written_line(self):
        import io

        import read_waitlist

        raw = io.StringIO(
            '{"email":"a@b.co","role":"lp","source":"hero","ts":100}\n'
            "\n"
            '{"email":"a@b.co","role":"both","source":"footer","ts":200}\n'
            '{"email":"c@d.co","role":"financier","source":"hero","ts":300}\n'
            "not json at all\n"
            '{"email":"e@f.co","ts":40'  # the append that was still in flight
        )
        rows = read_waitlist.read(raw)
        self.assertEqual([r["email"] for r in rows], ["a@b.co", "c@d.co"])
        # The first signup wins, so the timestamp is when they actually joined.
        self.assertEqual(rows[0]["ts"], 100)

    def test_unconfigured_refuses_instead_of_dropping(self):
        """With nowhere to deliver, the endpoint must say so. It used to default to a file in the
        working directory, which on a container is erased at the next deploy: the signup was
        answered 200 and then lost."""
        os.environ.pop("WAITLIST_FILE", None)
        status, _ = self.waitlist.process(b'{"email":"a@b.co"}')
        self.assertEqual(status, 503)


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
