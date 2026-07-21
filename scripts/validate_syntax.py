#!/usr/bin/env python3
"""
REO Syntax Validator — Check all Turtle files in the project
Usage: python scripts/validate_syntax.py
"""

import sys
from pathlib import Path

try:
    import rdflib
except ImportError:
    print("ERROR: rdflib not installed. Run: pip install rdflib")
    sys.exit(1)


def validate_file(filepath: Path) -> bool:
    g = rdflib.Graph()
    try:
        g.parse(str(filepath), format='turtle')
        print(f"✅ {filepath} — OK ({len(g)} triples)")
        return True
    except Exception as e:
        print(f"❌ {filepath} — FAILED: {e}")
        return False


def main():
    base = Path(__file__).parent.parent
    files = list(base.glob("ontology/*.ttl")) + list(base.glob("examples/**/*.ttl"))+ list(base.glob("test-cases/**/*.ttl"))

    if not files:
        print("No .ttl files found.")
        sys.exit(0)

    print("=== SYNTAX CHECK ===")
    all_ok = True
    for f in files:
        if not validate_file(f):
            all_ok = False

    if all_ok:
        print("✅ All Turtle files are valid.")
        sys.exit(0)
    else:
        print("❌ Some files have syntax errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()
