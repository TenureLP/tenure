"""Just enough secp256k1 to recover an Ethereum address from a signature. No dependencies.

Used by the paywall to prove that whoever presents a payment controls the account that sent it.
One recovery costs a few milliseconds, which is nothing next to the RPC round trips around it.
"""

from .keccak import keccak256

P = 2**256 - 2**32 - 977
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8


class BadSignature(Exception):
    pass


def _add(a, b):
    """Point addition in affine coordinates; None is the point at infinity."""
    if a is None:
        return b
    if b is None:
        return a
    ax, ay = a
    bx, by = b
    if ax == bx:
        if (ay + by) % P == 0:
            return None
        lam = 3 * ax * ax * pow(2 * ay, P - 2, P) % P
    else:
        lam = (by - ay) * pow(bx - ax, P - 2, P) % P
    x = (lam * lam - ax - bx) % P
    return (x, (lam * (ax - x) - ay) % P)


def _mul(point, k):
    k %= N
    result, addend = None, point
    while k:
        if k & 1:
            result = _add(result, addend)
        addend = _add(addend, addend)
        k >>= 1
    return result


def recover(msg_hash: bytes, signature: bytes) -> str:
    """Address that produced `signature` over `msg_hash`. Signature is 65 bytes: r || s || v."""
    if len(signature) != 65:
        raise BadSignature("signature must be 65 bytes")
    r = int.from_bytes(signature[0:32], "big")
    s = int.from_bytes(signature[32:64], "big")
    v = signature[64]
    if v >= 27:
        v -= 27
    if v not in (0, 1):
        raise BadSignature("bad recovery id")
    if not (1 <= r < N and 1 <= s < N):
        raise BadSignature("r or s out of range")
    # Reject the malleable high-s half, as Ethereum clients do.
    if s > N // 2:
        raise BadSignature("non-canonical s")

    # Lift r to a curve point whose y has the parity the recovery id asks for.
    y2 = (pow(r, 3, P) + 7) % P
    y = pow(y2, (P + 1) // 4, P)
    if pow(y, 2, P) != y2:
        raise BadSignature("r is not on the curve")
    if y % 2 != v:
        y = P - y

    e = int.from_bytes(msg_hash, "big")
    r_inv = pow(r, N - 2, N)
    point = _mul(_add(_mul((r, y), s), _mul((GX, GY), N - e)), r_inv)
    if point is None:
        raise BadSignature("recovery produced the point at infinity")
    raw = point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big")
    return "0x" + keccak256(raw)[12:].hex()


def personal_hash(message: str) -> bytes:
    """EIP-191 hash, what wallets sign for `personal_sign` / viem's `signMessage`."""
    body = message.encode()
    return keccak256(b"\x19Ethereum Signed Message:\n" + str(len(body)).encode() + body)
