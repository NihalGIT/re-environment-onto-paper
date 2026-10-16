#!/usr/bin/env python3
"""Run the complete REO v1.1.0 verification and evaluation pipeline.

Usage:  python scripts/run_all.py [--skip-corpus]
The corpus evaluation (scripts/run_evaluation.py) takes about 10-15 minutes
on two cores; --skip-corpus reuses results/evaluation_summary.json.
Java (for HermiT) is required by scripts/reasoner_check.py."""
import subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    ("Turtle syntax", ["scripts/validate_syntax.py"]),
    ("Artifact metrics and vocabulary inventory", ["scripts/artifact_metrics.py"]),
    ("Pitfall scan (OOPS! catalogue subset)", ["scripts/pitfall_scan.py"]),
    ("HermiT consistency and injected errors", ["scripts/reasoner_check.py"]),
    ("SHACL validation", ["scripts/run_shacl.py"]),
    ("Competency questions", ["scripts/run_competency_questions.py"]),
    ("Regression scenarios and targeted regressions", ["prototype.py"]),
    ("Seven-view derivation criteria", ["scripts/view_derivation.py"]),
    ("Identity migration cases", ["scripts/run_migration.py"]),
    ("Records and annotations outside the environment snapshot", ["scripts/check_record_isolation.py"]),
    ("Extension contract (vocabulary extension)", ["scripts/run_extension_check.py"]),
    ("v1.0.0 behaviour on the targeted cases", ["scripts/compare_v100.py"]),
    ("Mutation-corpus evaluation", ["scripts/run_evaluation.py"]),
    ("TF-IDF threshold sensitivity of the document baseline", ["scripts/ir_sensitivity.py"]),
    ("Language-model evaluation (re-score frozen outputs)", ["evaluation/llm-evaluation/scripts/rescore_all.py"]),
    ("Ontology diagram", ["scripts/draw_ontology.py"]),
    ("Paper macros and tables", ["scripts/export_paper_macros.py"]),
]

def main():
    skip = "--skip-corpus" in sys.argv
    failed = []
    for name, cmd in STEPS:
        if skip and cmd[0].endswith("run_evaluation.py"):
            print(f"[skip] {name}"); continue
        t = time.time()
        r = subprocess.run([sys.executable] + cmd, cwd=ROOT, capture_output=True, text=True)
        status = "ok" if r.returncode == 0 else "FAILED"
        print(f"[{status}] {name} ({time.time() - t:.0f}s)")
        if r.returncode:
            failed.append(name); print(r.stdout[-2000:], r.stderr[-2000:])
    print("All steps passed." if not failed else f"Failed steps: {failed}")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
