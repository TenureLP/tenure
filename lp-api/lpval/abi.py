"""Just enough ABI encoding/decoding for static-argument view calls."""

from .keccak import keccak256

WORD = 1 << 256


def selector(signature: str) -> bytes:
    return keccak256(signature.encode())[:4]


def enc_uint(x: int) -> bytes:
    return (x % WORD).to_bytes(32, "big")


enc_int = enc_uint  # two's complement via the modulo


def enc_addr(a: str) -> bytes:
    return bytes(12) + bytes.fromhex(a[2:].rjust(40, "0"))


def enc_bytes32(b: bytes) -> bytes:
    return b.rjust(32, b"\x00") if len(b) < 32 else b[:32]


def call_data(signature: str, *encoded_args: bytes) -> str:
    return "0x" + (selector(signature) + b"".join(encoded_args)).hex()


def words(data: bytes):
    return [int.from_bytes(data[i:i + 32], "big") for i in range(0, len(data) - len(data) % 32, 32)]


def to_signed(x: int, bits: int = 256) -> int:
    x &= (1 << bits) - 1
    return x - (1 << bits) if x >> (bits - 1) else x


def word_to_addr(w: int) -> str:
    return "0x" + (w & ((1 << 160) - 1)).to_bytes(20, "big").hex()


def decode_string(data: bytes) -> str:
    """Decodes a `string` return value; tolerates legacy bytes32 symbols."""
    if len(data) == 32:
        return data.rstrip(b"\x00").decode("utf-8", "replace")
    if len(data) < 64:
        return ""
    off = int.from_bytes(data[0:32], "big")
    n = int.from_bytes(data[off:off + 32], "big")
    return data[off + 32:off + 32 + n].decode("utf-8", "replace")
