#!/usr/bin/env python3
"""Re-score the frozen outputs of the language-model evaluation (E1-E3).

The agents are not re-run (their outputs vary between runs); this script
checks the freeze hashes, verifies that the E2 reference decisions still equal
the current corpus results, re-executes the E1 suites against the current
checker (without and with identity migration), re-scores E2 and E3, and writes
results/llm_evaluation_summary.json."""
import csv
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RAW, RES = HERE / "raw", HERE / "results"
S = HERE / "scripts"


def run(*args):
    subprocess.run([sys.executable, *map(str, args)], check=True, cwd=HERE, stdout=subprocess.DEVNULL)


def main():
    for e in json.loads((HERE / "freeze_record.json").read_text())["entries"]:
        h = hashlib.sha256((RAW / e["file"]).read_bytes()).hexdigest()
        assert h == e["sha256"], f"{e['file']} differs from its frozen hash"
    truth = json.loads((HERE / "e2" / "sample_truth.json").read_text())
    rows = list(csv.DictReader(gzip.open(ROOT / "results" / "mutants.csv.gz", "rt")))
    cur = {(r["mutant"], r["requirement"]): r["checker"] for r in rows}
    for c in truth["cases"]:
        for rid, st in c["truth"].items():
            assert cur[(c["mutant"], rid)] == st, f"E2 reference changed for {c['mutant']}/{rid}"
    suites = sorted(RAW.glob("E1_*_suite.json"))
    run(S / "run_llm_suite.py", "--no-migration", RES / "e1_run_initial_no_migration.json", *suites)
    run(S / "run_llm_suite.py", RES / "e1_run.json", *suites)
    answers = [RAW / f"E2_{c}_answers.json" for c in
               ("DOC-1", "DOC-2", "MODEL-1", "MODEL-2", "DOC-1r", "DOC-2r", "MODEL-1r", "MODEL-2r")]
    run(S / "score_e2.py", RES / "e2_scores.json", HERE / "e2" / "sample_truth.json", RAW / "audit.json",
        RAW / "agent_usage.json", *answers)
    run(S / "score_e3.py", RES / "e3_scores.json", RAW / "E3_B1_coding.json", RAW / "E3_B2_coding.json")
    run(S / "summarize.py")
    print("LLM evaluation re-scored; freeze hashes and E2 reference verified.")


if __name__ == "__main__":
    main()
