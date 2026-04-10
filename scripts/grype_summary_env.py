#!/usr/bin/env python3
"""
Print Grype severity counts as shell-assignable KEY=VALUE lines.
Usage: python3 scripts/grype_summary_env.py <sarif-file>
"""
import sys
sys.path.insert(0, "scripts")
from grype_sarif_summary import summarize

sarif_path = sys.argv[1] if len(sys.argv) > 1 else ""
s = summarize(sarif_path)
c = s["counts"] if s else {}

for key in ("critical", "high", "medium", "low", "negligible", "warning", "note"):
    print(f"{key.upper()}={c.get(key, 0)}")
