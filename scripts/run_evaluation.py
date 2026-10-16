#!/usr/bin/env python3
"""Mutation-corpus evaluation of the derivation contract (REO v1.1.0).

1. Generates a corpus of environment mutants with operators derived from the
   ontology schema and SHACL enumerations (not from the checker's branches).
2. For every mutant and every requirement of the ten-requirement set, runs
   (a) the reference checker, (b) the independent SPARQL encoding of the
   contract (differential testing), and (c) SHACL on the mutated graph.
3. Computes
   * checker/oracle agreement;
   * decision divergence of two schema-verdict baselines (global and
     requirement-focused SHACL) from the requirement-level contract;
   * change-impact precision/recall of six selection methods against the
     re-derivation ground truth, and their re-validation cost;
   * trace precision/recall of recorded traces and of an IR (TF-IDF)
     document-based baseline against behaviour-derived relevance;
   * an empirical check of trace sufficiency (Proposition 2);
   * structural modelling overhead and run time.

Writes results/evaluation_summary.json and results/mutants.csv.gz.
"""
from __future__ import annotations

import gzip
import csv
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

import rdflib
from rdflib import RDF, RDFS, BNode, Literal, URIRef, Namespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import reo_checker as R  # noqa: E402
import sparql_oracle as O  # noqa: E402

SH = Namespace("http://www.w3.org/ns/shacl#")
REO = R.REO
EX = R.EX
EXAMPLE = ROOT / "examples" / "medical-emergency"
ENV_FILES = [EXAMPLE / "hospital.ttl", EXAMPLE / "hospital-extension.ttl"]
REQ_FILE = EXAMPLE / "hospital-requirements.ttl"
SEVEN = R.SEVEN_VIEWS

# ---------------------------------------------------------------------------
# Corpus generation
# ---------------------------------------------------------------------------
def named(g):
    return sorted({s for s in g.subjects(RDF.type, None) if isinstance(s, URIRef)})


def view_index(g):
    env = R.project(g)
    idx = {}
    for v, d in env.views.items():
        for eid in d:
            idx[eid] = v
    return env, idx


def shacl_enumerations():
    shapes = R.load_graph([ROOT / "ontology" / "reo-shapes.ttl"])
    enums = {}
    for ps in shapes.subjects(SH["in"], None):
        path = shapes.value(ps, SH.path)
        lst = shapes.value(ps, SH["in"])
        enums[path] = [str(x) for x in shapes.items(lst)]
    return enums


def generate_corpus(g0: rdflib.Graph):
    env, idx = view_index(g0)
    onto = R.ontology_graph()
    individuals = {R.local(s): s for s in named(g0) if R.local(s) in idx}
    by_view = defaultdict(list)
    for eid, v in idx.items():
        by_view[v].append(eid)
    for v in by_view:
        by_view[v].sort()
    triples = sorted((s, p, o) for s, p, o in g0 if isinstance(s, URIRef) and not isinstance(o, BNode))
    muts, seen = [], set()

    def add(op, desc, rem=(), ad=()):
        rem = tuple(sorted(rem)); ad = tuple(sorted(t for t in ad if t not in g0))
        if not rem and not ad:
            return
        key = (rem, ad)
        if key in seen:
            return
        seen.add(key)
        muts.append({"id": f"M{len(muts) + 1:04d}", "op": op, "desc": desc, "remove": rem, "add": ad})

    # DEL-T: delete one asserted triple.
    for t in triples:
        add("DEL-T", f"delete {R.local(t[0])} {R.local(t[1])} {R.local(t[2])}", rem=[t])
    # DEL-E: delete every triple describing one element.
    for eid, s in individuals.items():
        add("DEL-E", f"delete element {eid}", rem=[t for t in triples if t[0] == s])
    # ENUM: replace an enumerated value by every other value allowed by the shapes.
    enums = shacl_enumerations()
    for s, p, o in triples:
        if p in enums:
            for alt in enums[p]:
                if alt != str(o):
                    add("ENUM", f"{R.local(s)}.{R.local(p)}: {o} -> {alt}", rem=[(s, p, o)],
                        ad=[(s, p, Literal(alt, datatype=o.datatype) if isinstance(o, Literal) else Literal(alt))])
    # AUTH: replace an authority value by every other authority value of the model.
    auth_vals = sorted({str(o) for o in g0.objects(None, REO.authorityLevel)})
    for s, p, o in triples:
        if p == REO.authorityLevel:
            for alt in auth_vals:
                if alt != str(o):
                    add("AUTH", f"{R.local(s)}.authority -> {alt}", rem=[(s, p, o)], ad=[(s, p, Literal(alt))])
    # DUP: add a second, different value to a single-valued interpreted attribute
    # (conflicting evidence, e.g., two sources reporting different authority levels).
    single_valued = {REO.authorityLevel: auth_vals, REO.protocol: ["HL7-v2"], REO.validatorKey: ["authority-equals",
                     "consent-or-exception"]}
    for pth, vals in enums.items():
        if pth in (REO.status, REO.enforcementLevel, REO.impactLevel):
            single_valued[pth] = vals
    for s, p, o in triples:
        if p in single_valued:
            alt = next((v for v in single_valued[p] if v != str(o)), None)
            if alt is not None:
                add("DUP", f"{R.local(s)}.{R.local(p)}: add conflicting value {alt}", ad=[(s, p, Literal(alt))])
    # RETARGET: replace the object of a link by another element of the same view.
    for s, p, o in triples:
        if p == RDF.type or not isinstance(o, URIRef) or R.local(o) not in idx:
            continue
        for alt in by_view[idx[R.local(o)]]:
            if alt != R.local(o):
                add("RETARGET", f"{R.local(s)}.{R.local(p)}: {R.local(o)} -> {alt}", rem=[(s, p, o)],
                    ad=[(s, p, individuals[alt])])
    # ADD-LINK: add a missing link for every object property, respecting domain/range views.
    root_view = {r: v for v, r in R.VIEW_ROOTS.items()}
    for p in sorted(set(onto.subjects(RDF.type, rdflib.OWL.ObjectProperty))):
        if not str(p).startswith(str(REO)) or p in (REO.supersededBy,):
            continue
        dom, rng = onto.value(p, RDFS.domain), onto.value(p, RDFS.range)
        if dom not in root_view:
            continue
        subs = by_view[root_view[dom]]
        if rng in root_view:
            objs = by_view[root_view[rng]]
        else:  # owl:Thing ranges: elements of the seven views
            objs = sorted(e for v in SEVEN for e in by_view[v])
        for s in subs:
            for o in objs:
                if s != o:
                    add("ADD-LINK", f"add {s} {R.local(p)} {o}", ad=[(individuals[s], p, individuals[o])])
    # NEW-RULE: a new hard constraint without validator, applying to one element.
    for eid in sorted(e for v in SEVEN for e in by_view[v]):
        c = EX[f"CNEW_{eid}"]
        add("NEW-RULE", f"new hard rule applying to {eid}", ad=[
            (c, RDF.type, REO.BusinessConstraint), (c, REO.constraintId, Literal(f"CNEW-{eid}")),
            (c, REO.constraintName, Literal("New rule")), (c, REO.formalExpression, Literal("manual_review")),
            (c, REO.naturalLanguage, Literal("A new rule.")), (c, REO.enforcementLevel, Literal("hard")),
            (c, REO.appliesTo, individuals[eid])])
    # NEW-UNC: a new unvalidated uncertainty affecting an element / blocking a goal.
    for eid in sorted(e for v in SEVEN for e in by_view[v]):
        for rel in (REO.affects, REO.blocks):
            if rel == REO.blocks and idx[eid] != "goals":
                continue
            u = EX[f"UNEW_{R.local(rel)}_{eid}"]
            add("NEW-UNC", f"new unvalidated uncertainty {R.local(rel)} {eid}", ad=[
                (u, RDF.type, REO.AssumptionUncertainty), (u, REO.uncertaintyId, Literal(f"UNEW-{eid}")),
                (u, REO.subject, Literal("New uncertainty.")), (u, REO.status, Literal("unvalidated")),
                (u, REO.impactLevel, Literal("high")), (u, REO.validationPlan, Literal("Review.")),
                (u, rel, individuals[eid])])
    return muts


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
_W = {}


def _init():
    g0 = R.load_graph(ENV_FILES)
    _W["g0"] = g0
    _W["req_graph"] = R.load_graph([REQ_FILE])
    _W["reqs"] = R.load_requirements(_W["req_graph"])
    _W["onto"] = R.load_graph(R.ONTOLOGY_FILES)
    _W["shapes"] = R.load_graph([ROOT / "ontology" / "reo-shapes.ttl"])


def assessment(res):
    return (res.state, tuple(sorted(res.justifications)))


def evaluate_mutant(m):
    g = rdflib.Graph()
    for t in _W["g0"]:
        g.add(t)
    for t in m["remove"]:
        g.remove(t)
    for t in m["add"]:
        g.add(t)
    t0 = time.perf_counter()
    env = R.project(g)
    results = {q.rid: R.validate(env, q) for q in _W["reqs"]}
    t1 = time.perf_counter()
    og = rdflib.Graph()
    for part in (_W["onto"], g, _W["req_graph"]):
        for t in part:
            og.add(t)
    oracle = O.decide(og)
    from pyshacl import validate
    conforms, rg, _ = validate(g, shacl_graph=_W["shapes"], ont_graph=_W["onto"], inference="rdfs",
                               allow_warnings=True)
    focus = defaultdict(set)
    for res in rg.subjects(RDF.type, SH.ValidationResult):
        sev = rg.value(res, SH.resultSeverity)
        fn = rg.value(res, SH.focusNode)
        focus["violation" if sev == SH.Violation else "warning"].add(R.local(fn))
    touched = {R.local(s) for s, _, _ in list(m["remove"]) + list(m["add"])}
    touched |= {R.local(o) for _, p, o in list(m["remove"]) + list(m["add"]) if isinstance(o, URIRef) and p != RDF.type}
    subjects = {R.local(s) for s, _, _ in list(m["remove"]) + list(m["add"])}
    return {"id": m["id"], "op": m["op"], "desc": m["desc"], "n_triples": len(m["remove"]) + len(m["add"]),
            "touched": sorted(touched), "subjects": sorted(subjects),
            "results": {rid: {"state": r.state, "assessment": assessment(r), "trace": sorted(r.trace)}
                        for rid, r in results.items()},
            "oracle": oracle, "validate_ms": (t1 - t0) * 1000 / max(1, len(results)),
            "shacl": {"violation_nodes": sorted(focus["violation"]), "warning_nodes": sorted(focus["warning"])}}


# ---------------------------------------------------------------------------
# IR baseline (TF-IDF over element descriptions)
# ---------------------------------------------------------------------------
STOP = {"the", "a", "an", "of", "to", "and", "or", "shall", "before", "each", "every", "in", "is", "be", "for",
        "on", "with", "that", "using", "via", "by", "from", "not", "yet", "any", "its", "it", "when", "must"}


def tokens(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return [w for w in re.findall(r"[a-z0-9]+", text.lower().replace("_", " ")) if w not in STOP and len(w) > 1]


def ir_documents(g0):
    docs = {}
    textual = [REO.actorName, REO.goalName, REO.conceptName, REO.constraintName, REO.contextName,
               REO.uncertaintyName, REO.interactionName, REO.propertyName, RDFS.label, REO.naturalLanguage,
               REO.subject]
    for s in named(g0):
        parts = [R.local(s)] + [str(o) for p in textual for o in g0.objects(s, p)]
        docs[R.local(s)] = tokens(" ".join(parts))
    return docs


def tfidf_links(docs, reqs):
    corpus = list(docs.values()) + [tokens(q.text) for q in reqs]
    n = len(corpus)
    df = Counter(w for d in corpus for w in set(d))
    idf = {w: math.log((1 + n) / (1 + c)) + 1 for w, c in df.items()}

    def vec(d):
        tf = Counter(d)
        v = {w: tf[w] * idf[w] for w in tf}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}
    ev = {e: vec(d) for e, d in docs.items()}
    sims = {}
    for q in reqs:
        qv = vec(tokens(q.text))
        sims[q.rid] = {e: sum(qv.get(w, 0) * x for w, x in v.items()) for e, v in ev.items()}
    return sims


# ---------------------------------------------------------------------------
def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn}


def main() -> int:
    _init()
    g0, reqs = _W["g0"], _W["reqs"]
    env0 = R.project(g0)
    base = {q.rid: R.validate(env0, q) for q in reqs}
    base_assess = {rid: assessment(r) for rid, r in base.items()}
    base_trace = {rid: set(r.trace) for rid, r in base.items()}
    seven_ids = {e for v in SEVEN for e in env0.views[v]}
    coarse_trace = {rid: t & seven_ids for rid, t in base_trace.items()}
    muts = generate_corpus(g0)
    print(f"Corpus: {len(muts)} mutants; operators {dict(Counter(m['op'] for m in muts))}", flush=True)
    t0 = time.time()
    with Pool(2, initializer=_init) as pool:
        rows = []
        for i, row in enumerate(pool.imap(evaluate_mutant, muts, chunksize=8)):
            rows.append(row)
            if (i + 1) % 200 == 0:
                print(f"  {i + 1}/{len(muts)} mutants ({time.time() - t0:.0f}s)", flush=True)
    rids = [q.rid for q in reqs]

    # A. Differential testing.
    pairs = [(row, rid) for row in rows for rid in rids]
    disagreements = [{"mutant": row["id"], "desc": row["desc"], "rid": rid,
                      "checker": row["results"][rid]["state"], "oracle": row["oracle"][rid]}
                     for row, rid in pairs if row["results"][rid]["state"] != row["oracle"][rid]]
    # B. Sensitivity.
    changed_any = [row for row in rows if any(tuple(map(tuple, [row["results"][r]["assessment"][0]])) != (base_assess[r][0],)
                                              for r in rids)]
    decision_changes = sum(row["results"][r]["state"] != base[r].state for row in rows for r in rids)
    by_op = defaultdict(lambda: [0, 0])
    for row in rows:
        by_op[row["op"]][1] += 1
        by_op[row["op"]][0] += any(row["results"][r]["state"] != base[r].state for r in rids)
    # C. Schema-verdict baselines.
    def shacl_global(row):
        if row["shacl"]["violation_nodes"]:
            return "rejected"
        return "conditional" if row["shacl"]["warning_nodes"] else "accepted"
    req_by_id = {q.rid: q for q in reqs}

    def focus_set(q):
        return q.references() | {q.seed_goal, q.context}

    def shacl_focused(row, rid):
        f = focus_set(req_by_id[rid])
        if f & set(row["shacl"]["violation_nodes"]):
            return "rejected"
        return "conditional" if f & set(row["shacl"]["warning_nodes"]) else "accepted"
    accept_like = {"accepted", "accepted_with_reservations"}
    baselines = {}
    for name, fn in (("shacl_global", lambda row, rid: shacl_global(row)), ("shacl_focused", shacl_focused)):
        conf = Counter(); fa = fr = agree = 0
        for row, rid in pairs:
            b, c = fn(row, rid), row["results"][rid]["state"]
            conf[(b, c)] += 1
            fa += b in accept_like and c not in accept_like
            fr += b == "rejected" and c in accept_like
            agree += (b == c) or (b == "accepted" and c in accept_like)
        baselines[name] = {"false_acceptance": fa, "false_rejection": fr, "agreement_broad": agree,
                           "pairs": len(pairs), "confusion": {f"{b}|{c}": n for (b, c), n in sorted(conf.items())}}
    # D. Change-impact precision/recall.
    sims = tfidf_links(ir_documents(g0), reqs)
    tau_grid = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3]
    ir_links = {tau: {rid: {e for e, s in sims[rid].items() if s >= tau} for rid in rids} for tau in tau_grid}
    impact = {}
    gold_kinds = {"assessment": lambda row, rid: tuple(map(lambda x: tuple(x) if isinstance(x, list) else x,
                                                           row["results"][rid]["assessment"])) != base_assess[rid],
                  "decision": lambda row, rid: row["results"][rid]["state"] != base[rid].state}

    def norm_assess(a):
        return (a[0], tuple(a[1]))
    for row in rows:
        for rid in rids:
            row["results"][rid]["assessment"] = norm_assess(row["results"][rid]["assessment"])
    gold_kinds["assessment"] = lambda row, rid: row["results"][rid]["assessment"] != base_assess[rid]

    def methods(row):
        touched, subjects = set(row["touched"]), set(row["subjects"])
        closure = R.dependency_closure(env0, subjects)
        return {
            "M1_fine_trace_touched_diff": {r for r in rids if base_trace[r] & touched},
            "M2_fine_trace_subject_diff": {r for r in rids if base_trace[r] & subjects},
            "M3_coarse_trace_subject_diff": {r for r in rids if coarse_trace[r] & subjects},
            "M4_coarse_trace_transitive_closure": {r for r in rids if coarse_trace[r] & closure},
            "M5_document_IR_tau_0.10": {r for r in rids if ir_links[0.1][r] & subjects},
            "M6_revalidate_all": set(rids),
        }
    sound_violations = []
    for gk, gfn in gold_kinds.items():
        acc = defaultdict(lambda: [0, 0, 0, 0])
        for row in rows:
            gold = {r for r in rids if gfn(row, r)}
            for name, sel in methods(row).items():
                a = acc[name]
                a[0] += len(sel & gold); a[1] += len(sel - gold); a[2] += len(gold - sel); a[3] += len(sel)
            if gk == "assessment":
                for r in gold:
                    if not (base_trace[r] & set(row["touched"])):
                        sound_violations.append({"mutant": row["id"], "desc": row["desc"], "rid": r})
        impact[gk] = {name: {**prf(a[0], a[1], a[2]), "mean_revalidations": a[3] / len(rows)}
                      for name, a in acc.items()}
        impact[gk]["_gold_pairs"] = sum(1 for row in rows for r in rids if gfn(row, r))
    # E. Trace precision/recall against behaviour-derived relevance.
    # Relevance = removing or altering an element's existing description changes the
    # assessment (operators that do not create links to other elements).
    single = [row for row in rows if row["op"] in ("DEL-T", "DEL-E", "ENUM", "AUTH")
              and len(row["subjects"]) == 1]
    relevant = defaultdict(set)
    for row in single:
        for r in rids:
            if row["results"][r]["assessment"] != base_assess[r]:
                relevant[r].add(row["subjects"][0])
    trace_eval = {}
    candidates = {"recorded_fine_trace": base_trace, "coarse_trace": coarse_trace}
    for tau in tau_grid:
        candidates[f"IR_tfidf_tau_{tau:.2f}"] = ir_links[tau]
    for name, links in candidates.items():
        tp = sum(len(links[r] & relevant[r]) for r in rids)
        fp = sum(len(links[r] - relevant[r]) for r in rids)
        fn = sum(len(relevant[r] - links[r]) for r in rids)
        trace_eval[name] = prf(tp, fp, fn)
    # F/G. Overhead and timing.
    req_g = _W["req_graph"]
    ann = {q.rid: sum(1 for _ in req_g.triples((R.REQ[q.rid], None, None))) for q in reqs}
    overhead = {
        "environment_triples": len(g0),
        "environment_elements_seven_views": len(seven_ids),
        "auxiliary_elements": sum(len(env0.views[v]) for v in ("actions", "properties", "invariants")),
        "annotation_triples_per_requirement": {"mean": sum(ann.values()) / len(ann), "min": min(ann.values()),
                                               "max": max(ann.values())},
        "references_per_requirement": {"mean": sum(len(q.references()) for q in reqs) / len(reqs)},
        "trace_size": {"mean": sum(len(t) for t in base_trace.values()) / len(base_trace),
                       "min": min(len(t) for t in base_trace.values()), "max": max(len(t) for t in base_trace.values())},
        "mean_validate_ms_per_requirement": sum(row["validate_ms"] for row in rows) / len(rows),
    }
    summary = {
        "policy_version": R.POLICY_VERSION, "requirements": rids,
        "baseline_decisions": {rid: base[rid].state for rid in rids},
        "corpus": {"mutants": len(rows), "by_operator": dict(Counter(row["op"] for row in rows)),
                   "pairs": len(pairs), "mutants_changing_some_decision": sum(v[0] for v in by_op.values()),
                   "decision_changes": decision_changes,
                   "by_operator_changing": {k: v for k, v in sorted(by_op.items())}},
        "differential": {"pairs": len(pairs), "agreements": len(pairs) - len(disagreements),
                         "disagreements": disagreements[:100], "n_disagreements": len(disagreements)},
        "baselines": baselines, "impact": impact,
        "trace_sufficiency": {"assessment_changes": impact["assessment"]["_gold_pairs"],
                              "missed_by_touched_trace": len(sound_violations), "examples": sound_violations[:20]},
        "trace_relevance": {"relevant_pairs": sum(len(v) for v in relevant.values()),
                            "relevant": {r: sorted(v) for r, v in relevant.items()}, "methods": trace_eval},
        "overhead": overhead, "runtime_seconds": time.time() - t0,
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "evaluation_summary.json").write_text(json.dumps(summary, indent=2, default=str),
                                                              encoding="utf-8")
    with gzip.open(ROOT / "results" / "mutants.csv.gz", "wt", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mutant", "operator", "description", "requirement", "checker", "oracle", "baseline_checker"])
        for row, rid in pairs:
            w.writerow([row["id"], row["op"], row["desc"], rid, row["results"][rid]["state"], row["oracle"][rid],
                        base[rid].state])
    print(json.dumps({k: summary[k] for k in ("corpus", "trace_sufficiency")}, indent=1, default=str))
    print("differential:", summary["differential"]["agreements"], "/", summary["differential"]["pairs"])
    for gk in impact:
        for name, v in impact[gk].items():
            if not name.startswith("_"):
                print(f"  impact[{gk}] {name:38s} P={v['precision']} R={v['recall']} cost={v['mean_revalidations']:.2f}")
    for name, v in trace_eval.items():
        print(f"  trace {name:28s} P={v['precision']} R={v['recall']} F1={v['f1']}")
    for name, v in baselines.items():
        print(f"  baseline {name}: FA={v['false_acceptance']} FR={v['false_rejection']} agree={v['agreement_broad']}/{v['pairs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
