import base64
import zlib

import pytest
from routers.best9 import _MAX_DECOMPRESSED_BYTES, _MAX_Z_LEN, _decompress_ids


def _compress(payload: bytes) -> str:
    """deflate-raw + base64url（パディング除去）で圧縮し、z パラメータ文字列を返す。"""
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    comp = co.compress(payload) + co.flush()
    return base64.urlsafe_b64encode(comp).decode().rstrip("=")


def test_roundtrip_decodes_ids():
    z = _compress(b"a,b,c")
    assert _decompress_ids(z) == ["a", "b", "c"]


def test_limits_result_to_9_ids():
    z = _compress(",".join(str(i) for i in range(20)).encode())
    assert _decompress_ids(z) == [str(i) for i in range(9)]


def test_rejects_oversized_compressed_input():
    """巨大な z パラメータは展開前に拒否する。"""
    with pytest.raises(ValueError):
        _decompress_ids("A" * (_MAX_Z_LEN + 1))


def test_rejects_decompression_bomb():
    """圧縮データは入力上限以内なのに、展開後が巨大になる解凍爆弾を拒否する。

    入力長チェック（_MAX_Z_LEN）ではなく、展開時上限（_MAX_DECOMPRESSED_BYTES）で
    弾けることを保証する回帰テスト。
    """
    payload = ("a," * 500_000).encode()  # 展開後 ~1MB
    z = _compress(payload)
    # 圧縮後は入力上限以内（= 入力長チェックは素通りする）が、展開後は上限を大きく超える
    assert len(z) <= _MAX_Z_LEN
    assert len(payload) > _MAX_DECOMPRESSED_BYTES
    with pytest.raises(ValueError):
        _decompress_ids(z)


def test_accepts_payload_at_decompressed_limit():
    """上限ぎりぎりの正常データは展開できる。"""
    payload = b"x" * (_MAX_DECOMPRESSED_BYTES - 100)
    z = _compress(payload)
    assert _decompress_ids(z) == [payload.decode()]
