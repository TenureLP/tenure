import unittest

from lpval import abi, v4math
from lpval.keccak import keccak256


class KeccakTest(unittest.TestCase):
    def test_known_vectors(self):
        self.assertEqual(
            keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
        )
        self.assertEqual(abi.selector("transfer(address,uint256)").hex(), "a9059cbb")
        self.assertEqual(abi.selector("balanceOf(address)").hex(), "70a08231")

    def test_multi_block_input(self):
        # longer than one 136-byte rate block
        try:
            from Crypto.Hash import keccak as ref
        except ImportError:
            self.skipTest("pycryptodome not installed")
        data = bytes(range(256)) * 3
        self.assertEqual(keccak256(data), ref.new(digest_bits=256, data=data).digest())


class TickMathTest(unittest.TestCase):
    def test_canonical_values(self):
        self.assertEqual(v4math.sqrt_ratio_at_tick(0), 1 << 96)
        self.assertEqual(v4math.sqrt_ratio_at_tick(v4math.MIN_TICK), 4295128739)
        self.assertEqual(v4math.sqrt_ratio_at_tick(v4math.MAX_TICK), 1461446703485210103287273052203988822378723970342)

    def test_monotonic_and_matches_float(self):
        prev = 0
        for t in range(-200000, 200001, 12345):
            s = v4math.sqrt_ratio_at_tick(t)
            self.assertGreater(s, prev)
            prev = s
            self.assertAlmostEqual((s / v4math.Q96) ** 2 / (1.0001 ** t), 1.0, places=9)


class AmountsTest(unittest.TestCase):
    def setUp(self):
        self.a = v4math.sqrt_ratio_at_tick(-600)
        self.b = v4math.sqrt_ratio_at_tick(600)
        self.L = 10 ** 18

    def test_below_range_is_all_token0(self):
        a0, a1 = v4math.amounts_for_liquidity(v4math.sqrt_ratio_at_tick(-1000), self.a, self.b, self.L)
        self.assertGreater(a0, 0)
        self.assertEqual(a1, 0)

    def test_above_range_is_all_token1(self):
        a0, a1 = v4math.amounts_for_liquidity(v4math.sqrt_ratio_at_tick(1000), self.a, self.b, self.L)
        self.assertEqual(a0, 0)
        self.assertGreater(a1, 0)

    def test_symmetric_range_at_price_one(self):
        a0, a1 = v4math.amounts_for_liquidity(1 << 96, self.a, self.b, self.L)
        self.assertAlmostEqual(a0 / a1, 1.0, places=6)

    def test_fee_growth_wraps(self):
        last = (1 << 256) - 5
        now = 10
        self.assertEqual(v4math.fees_owed(now, last, 1 << 128), 15)


class AbiTest(unittest.TestCase):
    def test_signed_roundtrip(self):
        self.assertEqual(abi.to_signed(int.from_bytes(abi.enc_int(-600), "big")), -600)
        self.assertEqual(abi.to_signed(0xFFFDA8, 24), -600)

    def test_string_decoding(self):
        data = (32).to_bytes(32, "big") + (4).to_bytes(32, "big") + b"USDG".ljust(32, b"\x00")
        self.assertEqual(abi.decode_string(data), "USDG")


if __name__ == "__main__":
    unittest.main()
