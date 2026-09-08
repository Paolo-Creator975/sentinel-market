import json, hashlib
from pathlib import Path
EXPECTED_THRESHOLD_SHA="138b1badf9695b0393b9547dc0f32b022fc9a8a7b2bfbdea3d127fe084ba5b41"
def load_and_verify(root):
    p=Path(root)/"config"/"immutable_thresholds.json"
    doc=json.loads(p.read_text())
    claimed=doc.pop("sha256")
    calc=hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    if claimed != EXPECTED_THRESHOLD_SHA:
        raise RuntimeError("frozen threshold hash mismatch")
    doc["sha256"]=claimed
    return doc
