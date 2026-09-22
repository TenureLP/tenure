"""The wallet view: finding a wallet's positions, reading its hooks, and what is said about each.

No network. The chain is a fake that answers exactly what each test needs.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lpval import abi, portfolio  # noqa: E402
from lpval.rpc import REVERTED, UNAVAILABLE, RpcError, UpstreamError  # noqa: E402

OWNER = "0x" + "ab" * 20
OTHER = "0x" + "cd" * 20


def _transfer(token_id):
    return {"topics": [portfolio.TRANSFER, "0x" + "0" * 64, "0x" + "0" * 24 + OWNER[2:], hex(token_id)]}


class LogRpc:
    """Endpoints are names. Each answers eth_getLogs from a script: a list of logs, or an exception."""

    def __init__(self, script, owners=None, head=1_000_000):
        self.endpoints = list(script)
        self.script = script
        self.owners = owners or {}
        self.head = head
        self.asked = []

    def request_on(self, method, params, endpoint, timeout=None):
        self.asked.append((endpoint, params[0].get("fromBlock"), params[0].get("toBlock")))
        answer = self.script[endpoint]
        if callable(answer):
            answer = answer(params[0])
        if isinstance(answer, Exception):
            raise answer
        return answer

    def block_number(self):
        return self.head

    def batch(self, reqs, endpoints=None):
        out = []
        for _, params in reqs:
            token_id = int(params[0]["data"][10:], 16)
            if token_id in self.flaky:
                self.flaky.discard(token_id)  # refused once for going too fast, fine the next time
                out.append(UNAVAILABLE)
                continue
            owner = self.owners.get(token_id)
            out.append(REVERTED if owner is None else "0x" + abi.enc_addr(owner).hex())
        return out

    flaky = set()


class DiscoveryTest(unittest.TestCase):
    def test_the_first_endpoint_that_serves_the_range_wins(self):
        rpc = LogRpc({
            "archive": RpcError("eth_getLogs: up to a 10 block range"),
            "public": [_transfer(5), _transfer(9), _transfer(5)],
        })
        ids, complete = portfolio.received_token_ids(rpc, OWNER)
        self.assertEqual(ids, [9, 5])
        self.assertTrue(complete)

    def test_a_wallet_too_busy_to_list_whole_is_walked_back_from_the_head(self):
        """A market-making bot has received more positions than a node returns in one answer. The
        newest are what matter, so they are gathered first and the answer says it is partial."""
        def public(q):
            if q["fromBlock"] == "0x0" and q["toBlock"] == "latest":
                return RpcError("logs matched by query exceeds limit of 10000")
            lo, hi = int(q["fromBlock"], 16), int(q["toBlock"], 16)
            return [_transfer(b) for b in range(max(lo, hi - 30), hi + 1)]
        rpc = LogRpc({"public": public})
        ids, complete = portfolio.received_token_ids(rpc, OWNER, want=60)
        self.assertEqual(len(ids), 60)
        self.assertEqual(ids[0], rpc.head)
        self.assertFalse(complete)

    def test_a_refused_window_shrinks_instead_of_failing(self):
        def public(q):
            if q["toBlock"] == "latest":
                return RpcError("exceeds limit of 10000")
            lo, hi = int(q["fromBlock"], 16), int(q["toBlock"], 16)
            if hi - lo > 5_000:
                return RpcError("logs matched by query exceeds limit of 10000")
            return [_transfer(hi)]
        rpc = LogRpc({"public": public})
        ids, _ = portfolio.received_token_ids(rpc, OWNER, want=3)
        self.assertEqual(len(ids), 3)

    def test_a_rate_limit_is_waited_out_not_reported(self):
        calls = {"n": 0}

        def public(q):
            calls["n"] += 1
            return UpstreamError("HTTP 429 from rpc") if calls["n"] == 1 else [_transfer(7)]
        orig = portfolio.time.sleep
        portfolio.time.sleep = lambda s: None
        try:
            ids, _ = portfolio.received_token_ids(LogRpc({"public": public}), OWNER)
        finally:
            portfolio.time.sleep = orig
        self.assertEqual(ids, [7])

    def test_only_tokens_still_held_are_kept(self):
        rpc = LogRpc({"public": []}, owners={1: OWNER, 2: OTHER})  # 3 was burnt: ownerOf reverts
        self.assertEqual(portfolio.still_owned(rpc, OWNER, [1, 2, 3]), ([1], True))

    def test_items_a_metered_provider_refused_are_asked_again(self):
        """Alchemy answers part of a batch and refuses the rest for exceeding its rate. The answers
        that did come back are kept and only the refused ones are asked again."""
        rpc = LogRpc({"a": [], "b": []}, owners={1: OWNER, 2: OWNER, 3: OWNER})
        rpc.flaky = {2, 3}
        orig = portfolio.time.sleep
        portfolio.time.sleep = lambda s: None
        try:
            self.assertEqual(portfolio.still_owned(rpc, OWNER, [1, 2, 3]), ([1, 2, 3], True))
        finally:
            portfolio.time.sleep = orig


    def test_a_long_history_stops_once_enough_are_held(self):
        """Three thousand ids cost a minute to check and the oldest are what nobody is waiting for.
        The walk stops early and says the list is not exhaustive."""
        ids = list(range(3000, 0, -1))
        rpc = LogRpc({"public": []}, owners={t: OWNER for t in ids})
        held, checked_all = portfolio.still_owned(rpc, OWNER, ids, want=60, cap=600)
        self.assertEqual(len(held), 100)  # the batches already in flight when the limit was reached
        self.assertEqual(held[0], 3000)
        self.assertFalse(checked_all)


class HookTest(unittest.TestCase):
    def test_no_hook_is_no_hook(self):
        self.assertIsNone(portfolio.hook_permissions("0x" + "00" * 20)["address"])

    def test_permissions_are_read_from_the_address(self):
        # The ETH / USDG pool on Robinhood Chain: beforeInitialize and beforeSwap, dynamic fee.
        h = portfolio.hook_permissions("0x06a889870c8f83640d6816319f72e2aa579b6080", 0x800000)
        self.assertEqual(h["permissions"], ["beforeInitialize", "beforeSwap"])
        self.assertTrue(h["dynamicFee"])
        self.assertEqual({e["level"] for e in h["effects"]}, {"info"})

    def test_a_hook_that_can_take_from_withdrawals_is_flagged_as_the_worst_case(self):
        h = portfolio.hook_permissions("0x" + "00" * 18 + "03" + "01")  # bits 9, 8 and 0
        self.assertIn("afterRemoveLiquidityReturnDelta", h["permissions"])
        self.assertEqual(h["effects"][0]["level"], "bad")

    def test_a_hook_that_runs_on_withdrawal_is_a_warning(self):
        h = portfolio.hook_permissions("0x" + "00" * 18 + "02" + "00")  # bit 9
        self.assertEqual(h["permissions"], ["beforeRemoveLiquidity"])
        self.assertEqual(h["effects"][0]["level"], "warn")


def _val(tick=0, tl=-600, tu=600, liquidity=10**18, fees=0.0, principal=1000.0, apr=20.0, hooks=None, subscriber=False):
    return {
        "pool": {"token0": {"symbol": "ETH"}, "token1": {"symbol": "USDG"}, "hooks": hooks or "0x" + "00" * 20, "keyFeePips": 500},
        "position": {"tickLower": tl, "tickUpper": tu, "liquidity": str(liquidity), "inRange": tl <= tick < tu, "hasSubscriber": subscriber},
        "price": {"tick": tick},
        "valueUSDG": {"principal": principal, "fees": fees, "total": principal + fees},
        "feeRate": {"available": True, "plausible": True, "feeAprPercent": apr, "windowSeconds": 86400},
    }


class DiagnoseTest(unittest.TestCase):
    def kinds(self, findings):
        return [f["kind"] for f in findings]

    def test_a_healthy_position_says_little(self):
        self.assertEqual(self.kinds(portfolio.diagnose(_val())), [])

    def test_out_of_range_is_first_and_names_the_side(self):
        f = portfolio.diagnose(_val(tick=800, fees=20))
        self.assertEqual(f[0]["kind"], "out-of-range")
        self.assertIn("entirely USDG", f[0]["detail"])

    def test_below_the_range_the_position_is_all_token0(self):
        f = portfolio.diagnose(_val(tick=-900))
        self.assertIn("entirely ETH", f[0]["detail"])

    def test_close_to_an_edge_is_a_warning(self):
        f = portfolio.diagnose(_val(tick=560))  # 40 ticks from the top, about 0.4%
        self.assertEqual(f[0]["kind"], "near-edge")
        self.assertIn("upper", f[0]["title"])

    def test_fees_worth_collecting_are_mentioned_and_dust_is_not(self):
        self.assertIn("fees-waiting", self.kinds(portfolio.diagnose(_val(fees=25))))
        self.assertNotIn("fees-waiting", self.kinds(portfolio.diagnose(_val(fees=0.5))))

    def test_an_empty_position_is_only_empty(self):
        self.assertEqual(self.kinds(portfolio.diagnose(_val(liquidity=0, tick=5000))), ["empty"])

    def test_a_lease_is_offered_only_when_one_is_possible(self):
        lease = {"available": True, "suggestedSalePriceUSDG": 800.0, "suggestedRentUSDG": 12.5, "termDays": 7}
        self.assertIn("tenure", self.kinds(portfolio.diagnose(_val(), lease)))
        self.assertNotIn("tenure", self.kinds(portfolio.diagnose(_val(subscriber=True), lease)))
        # Out of range the vault refuses the listing, so offering it would be offering a revert.
        self.assertNotIn("tenure", self.kinds(portfolio.diagnose(_val(tick=900), lease)))

    def test_findings_never_tell_anyone_what_to_do(self):
        """Facts and options. A finding that reads as an order is advice, which this is not."""
        lease = {"available": True, "suggestedSalePriceUSDG": 800.0, "suggestedRentUSDG": 12.5, "termDays": 7}
        cases = [_val(tick=800, fees=40), _val(tick=560, apr=0.2), _val(liquidity=0),
                 _val(hooks="0x" + "00" * 18 + "03" + "01", subscriber=True)]
        for val in cases:
            for f in portfolio.diagnose(val, lease):
                text = (f["title"] + " " + f["detail"]).lower()
                for word in ("you should", "we recommend", "must ", "buy ", "sell "):
                    self.assertNotIn(word, text, f)


if __name__ == "__main__":
    unittest.main()
