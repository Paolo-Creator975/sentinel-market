
import json, hashlib
from pathlib import Path

EXPECTED_THRESHOLD_SHA="138b1badf9695b0393b9547dc0f32b022fc9a8a7b2bfbdea3d127fe084ba5b41"
EXPECTED_DONCHIAN_SHA="866ae4aef86fa42abe6f02b57db2c2c563189a8de2c6c0c732c1a75716fbe855"
EXPECTED_CRYPTO24_SHA="42e3cd9fdf9515a7144663f222de296dd8f13b9c6160c202549c8624c8a97fde"

def load_and_verify(root):
    p=Path(root)/"config"/"immutable_thresholds.json"
    doc=json.loads(p.read_text())
    claimed=doc.get("sha256")
    if claimed != EXPECTED_THRESHOLD_SHA:
        raise RuntimeError(f"frozen threshold hash mismatch: {claimed} != {EXPECTED_THRESHOLD_SHA}")
    return doc

def load_and_verify_donchian(root):
    p=Path(root)/"config"/"donchian_trend_14d_v1.json"
    doc=json.loads(p.read_text())
    claimed=doc.pop("sha256")
    calc=hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if claimed != calc:
        raise RuntimeError(f"Donchian document self-hash mismatch: {claimed} != {calc}")
    if claimed != EXPECTED_DONCHIAN_SHA:
        raise RuntimeError(f"frozen Donchian hash mismatch: {claimed} != {EXPECTED_DONCHIAN_SHA}")
    doc["sha256"]=claimed
    return doc

def load_crypto_24h_candidate(root):
    p=Path(root)/"config"/"crypto_24h_demo_v1.json"
    doc=json.loads(p.read_text())
    if doc.get("status") != "SHADOW_PAPER_FROZEN" or not doc.get("immutable_for_demo") or not doc.get("paper_positions_enabled"):
        raise RuntimeError("Crypto 24H must remain a paper-only shadow demo")
    if doc.get("execution_enabled") or doc.get("real_trading_enabled"):
        raise RuntimeError("Crypto 24H cannot execute real positions")
    canonical=json.dumps(doc,sort_keys=True,separators=(",",":")).encode()
    doc["sha256"]=hashlib.sha256(canonical).hexdigest()
    if doc["sha256"] != EXPECTED_CRYPTO24_SHA:
        raise RuntimeError("frozen Crypto 24H configuration hash mismatch")
    return doc
