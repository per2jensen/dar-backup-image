import hashlib
from pathlib import Path

def sha256sum(path):
    """Compute SHA256 for a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def compare_to_originals(originals_dir, data_dir):
    """Compare files between two directories by hash."""
    mismatches = []
    originals = Path(originals_dir)
    current = Path(data_dir)
    for file in originals.glob("*"):
        cur = current / file.name
        if not cur.exists():
            mismatches.append((file.name, "missing"))
            continue
        if sha256sum(file) != sha256sum(cur):
            mismatches.append((file.name, "hash_mismatch"))
    return mismatches


