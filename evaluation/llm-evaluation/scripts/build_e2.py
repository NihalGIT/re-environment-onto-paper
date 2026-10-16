#!/usr/bin/env python3
"""Build the materials of study E2 (LLM analysts applying the contract by hand).

A stratified random sample of the schema-derived mutation corpus (seed 2026) is
presented to LLM analysts in two conditions:

* DOC   - documentation-based: the environment verbalised as prose (one paragraph
          per element, generated mechanically from the Turtle, so the information
          content is identical), requirements as text with their goal and context
          only (no explicit mapping), each change verbalised as prose;
* MODEL - model-based without the checker: the REO Turtle files, the explicit
          requirement annotations, each change as Turtle triples removed/added.

Both conditions receive the published specification (SPEC.md) and the decisions
of R001-R010 on the unmodified model. The expected decisions (ground truth) are
the decisions of the reference checker, which agree with the independent SPARQL
oracle on every pair; they are written outside the analysts' folders.

Usage: python build_e2.py <sandbox_root> <n_changing> <n_unchanged>
"""
from __future__ import annotations

import csv
import gzip
import json
import random
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import rdflib
from rdflib import RDF, Literal, URIRef

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import reo_checker as R  # noqa: E402
import run_evaluation as E  # noqa: E402

HERE = ROOT / "evaluation" / "llm-evaluation"
SPEC = HERE / "spec"
SEED = 2026


def words(p: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", R.local(p)).lower()


def term(o) -> str:
    if isinstance(o, URIRef):
        return R.local(o)
    if isinstance(o, Literal):
        return f'"{o}"'
    return str(o)


def verbalise_graph(g: rdflib.Graph) -> str:
    out = []
    subjects = sorted({s for s in g.subjects() if isinstance(s, URIRef)}, key=R.local)
    for s in subjects:
        types = sorted(R.local(t) for t in g.objects(s, RDF.type))
        lines = [f"**{R.local(s)}** — kind: {', '.join(types) if types else 'unspecified'}."]
        by_p = defaultdict(list)
        for p, o in g.predicate_objects(s):
            if p != RDF.type:
                by_p[words(p)].append(term(o))
        for p in sorted(by_p):
            lines.append(f"  - {p}: {'; '.join(sorted(by_p[p]))}")
        out.append("\n".join(lines))
    return "\n\n".join(out)


def verbalise_triple(t) -> str:
    s, p, o = t
    if p == RDF.type:
        return f"{R.local(s)} is of kind {R.local(o)}"
    return f"{R.local(s)} — {words(p)} — {term(o)}"


def turtle_of(triples) -> str:
    g = rdflib.Graph()
    g.bind("reo", R.REO); g.bind("ex", R.EX)
    for t in triples:
        g.add(t)
    txt = g.serialize(format="turtle")
    return "\n".join(l for l in txt.splitlines() if not l.startswith("@prefix")).strip()


def main(sandbox_root, n_changing, n_unchanged):
    n_changing, n_unchanged = int(n_changing), int(n_unchanged)
    g0 = R.load_graph(E.ENV_FILES)
    corpus = {m["id"]: m for m in E.generate_corpus(g0)}
    rows = list(csv.DictReader(gzip.open(ROOT / "results" / "mutants.csv.gz", "rt")))
    truth = defaultdict(dict)
    for r in rows:
        assert r["checker"] == r["oracle"]
        truth[r["mutant"]][r["requirement"]] = r["checker"]
    base = json.loads((ROOT / "results" / "evaluation_summary.json").read_text())["baseline_decisions"]
    changing = defaultdict(list); unchanged = defaultdict(list)
    for mid, dec in sorted(truth.items()):
        op = corpus[mid]["op"]
        (changing if any(dec[r] != base[r] for r in dec) else unchanged)[op].append(mid)
    rng = random.Random(SEED)

    def stratified(pool, n):
        ops = sorted(pool); picks = []
        for op in ops:
            rng.shuffle(pool[op])
        while len(picks) < n and any(pool[o] for o in ops):
            for op in ops:
                if pool[op] and len(picks) < n:
                    picks.append(pool[op].pop())
        return picks
    sample = stratified(changing, n_changing) + stratified(unchanged, n_unchanged)
    rng.shuffle(sample)
    items = []
    for i, mid in enumerate(sample, 1):
        m = corpus[mid]
        items.append({"case": f"C{i:02d}", "mutant": mid, "operator": m["op"],
                      "remove": [verbalise_triple(t) for t in m["remove"]],
                      "add": [verbalise_triple(t) for t in m["add"]],
                      "remove_turtle": turtle_of(m["remove"]), "add_turtle": turtle_of(m["add"]),
                      "truth": truth[mid]})
    root = Path(sandbox_root)
    # Ground truth stays outside the analysts' folders.
    (HERE / "e2").mkdir(parents=True, exist_ok=True)
    (HERE / "e2" / "sample_truth.json").write_text(json.dumps(
        {"seed": SEED, "base_decisions": base,
         "cases": [{k: it[k] for k in ("case", "mutant", "operator", "truth")} for it in items]}, indent=1))
    env_doc = verbalise_graph(R.load_graph(E.ENV_FILES))
    reqg = R.load_graph([E.REQ_FILE])
    req_doc = "\n".join(f"* **{q.rid}** (goal {q.seed_goal}, context {q.context}): {q.text}"
                        for q in R.load_requirements(reqg))
    base_tbl = "\n".join(f"| {r} | {s} |" for r, s in sorted(base.items()))
    for cond in ("DOC", "MODEL"):
        d = root / f"E2-{cond}"
        (d / "spec").mkdir(parents=True, exist_ok=True); (d / "out").mkdir(exist_ok=True)
        shutil.copy(SPEC / "SPEC.md", d / "spec" / "SPEC.md")
        if cond == "MODEL":
            for f in ("reo-core.ttl", "reo-derivation.ttl", "hospital.ttl", "hospital-extension.ttl",
                      "hospital-requirements.ttl"):
                shutil.copy(SPEC / f, d / "spec" / f)
            cases = [{"case": it["case"], "remove_turtle": it["remove_turtle"], "add_turtle": it["add_turtle"]}
                     for it in items]
        else:
            (d / "spec" / "environment.md").write_text(
                "# Emergency-prescription environment (documentation)\n\nEach paragraph documents one "
                "element of the environment and its attributes and relations.\n\n" + env_doc + "\n")
            (d / "spec" / "requirements.md").write_text(
                "# Requirements\n\nEach requirement is assessed for the stated goal and context.\n\n" + req_doc + "\n")
            cases = [{"case": it["case"], "removed_statements": it["remove"], "added_statements": it["add"]}
                     for it in items]
        (d / "spec" / "base_decisions.md").write_text(
            "# Decisions on the unmodified environment\n\n| Requirement | Decision |\n|---|---|\n" + base_tbl + "\n")
        (d / "spec" / "changes.json").write_text(json.dumps(cases, indent=1))
        shutil.copy(HERE / "tasks" / f"TASK_E2_{cond.lower()}.md", d / "TASK.md")
    print(f"sample: {len(items)} cases ({n_changing} changing, {n_unchanged} unchanged); "
          f"operators: {sorted({it['operator'] for it in items})}")


if __name__ == "__main__":
    main(*sys.argv[1:])
