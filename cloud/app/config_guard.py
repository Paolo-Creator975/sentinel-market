
import json, hashlib
from pathlib import Path

EXPECTED_THRESHOLD_SHA="138b1badf9695b0393b9547dc0f32b022fc9a8a7b2bfbdea3d127fe084ba5b41"
EXPECTED_DONCHIAN_SHA="866ae4aef86fa42abe6f02b57db2c2c563189a8de2c6c0c732c1a75716fbe855"

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
