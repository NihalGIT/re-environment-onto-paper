#!/usr/bin/env python3
"""Freeze LLM-authored files before execution: record SHA-256, size and UTC time.

Usage: python freeze.py <freeze_record.json> <file> [...]
The record is append-only: existing entries are kept and a file frozen twice
with different content is reported as an error."""
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

def main(record, *files):
    rp = Path(record)
    rec = json.loads(rp.read_text()) if rp.exists() else {"entries": []}
    known = {e["file"]: e["sha256"] for e in rec["entries"]}
    for f in files:
        p = Path(f); h = hashlib.sha256(p.read_bytes()).hexdigest()
        if p.name in known:
            if known[p.name] != h:
                raise SystemExit(f"{p.name}: content changed after freeze")
            continue
        rec["entries"].append({"file": p.name, "sha256": h, "bytes": p.stat().st_size,
                               "frozen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    rp.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))

if __name__ == "__main__":
    main(*sys.argv[1:])
