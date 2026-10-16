#!/usr/bin/env python3
"""Export every number reported in the paper from results/*.json.

Writes generated/results_macros.tex (\\newcommand definitions) and LaTeX table
bodies generated/tab_*.tex, so the manuscript cannot drift from the run."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
GEN = ROOT / "generated"


def load(name):
    return json.loads((RES / name).read_text(encoding="utf-8"))


def pct(x, digits=1):
    return f"{100 * x:.{digits}f}\\%"


def f2(x):
    return "--" if x is None else f"{x:.2f}"


def main() -> int:
    GEN.mkdir(exist_ok=True)
    m = {}
    met = load("artifact_metrics.json")
    m["CoreTriples"] = met["core"]["triples"]
    m["DerivTriples"] = met["derivation"]["triples"]
    m["OntoClasses"] = met["ontology_total"]["classes"]
    m["CoreClasses"] = met["core"]["classes"]
    m["DerivClasses"] = met["derivation"]["classes"]
    m["OntoObjProps"] = met["ontology_total"]["object_properties"]
    m["CoreObjProps"] = met["core"]["object_properties"]
    m["DerivObjProps"] = met["derivation"]["object_properties"]
    m["OntoDataProps"] = met["ontology_total"]["datatype_properties"]
    m["CoreDataProps"] = met["core"]["datatype_properties"]
    m["DerivDataProps"] = met["derivation"]["datatype_properties"]
    m["ShapeTriples"] = met["shapes"]["triples"] + met["derivation_shapes"]["triples"]
    m["NodeShapes"] = met["shapes"]["node_shapes"] + met["derivation_shapes"]["node_shapes"]
    m["PropShapes"] = met["shapes"]["property_shapes"] + met["derivation_shapes"]["property_shapes"]
    m["SparqlConstraints"] = met["shapes"]["sparql_constraints"] + met["derivation_shapes"]["sparql_constraints"]
    m["TurtleFiles"] = met["turtle_file_count"]
    m["TotalTriples"] = f"{met['total_triples']:,}"
    tb = met["triples_by_file"]
    m["HospitalTriples"] = tb["examples/medical-emergency/hospital.ttl"]
    m["ExtensionTriples"] = tb["examples/medical-emergency/hospital-extension.ttl"]
    m["ReqTriples"] = tb["examples/medical-emergency/hospital-requirements.ttl"]

    pit = load("pitfall_results.json")
    for v, tag in (("v1.0.0", "Old"), ("v1.1.0", "New")):
        r = pit[v]
        m[f"Pit{tag}Annot"] = len(r["P08_missing_annotations"])
        m[f"Pit{tag}Disj"] = len(r["P10_top_classes_without_disjointness"])
        m[f"Pit{tag}DomRange"] = len(r["P11_missing_domain_or_range"])
        m[f"Pit{tag}License"] = len(r["P41_no_license"])
        m[f"Pit{tag}Unconnected"] = len(r["P04_unconnected"])
        m[f"Pit{tag}Naming"] = len(r["P22_naming"])

    rea = load("reasoner_results.json")
    neg = rea["negative"]
    m["ReasNegTotal"] = len(neg)
    m["ReasNegNew"] = sum(v["v1_1_detected"] for v in neg.values())
    old = [v for v in neg.values() if "v1_0_detected" in v]
    m["ReasNegOldTotal"] = len(old)
    m["ReasNegOld"] = sum(v["v1_0_detected"] for v in old)
    m["ReasFullTriples"] = f"{rea['positive']['P3_all_modules_example_extension_requirements_records']['triples']:,}"

    sh = load("shacl_results.json")
    m["ShaclNegViol"] = sh["fixture_03_violations"]["violations"]

    cq = load("cq_results.json")
    m["CQPass"], m["CQTotal"] = cq["passed"], cq["total"]
    ck = cq["coverage_by_kind"]
    m["CQCovObj"], m["CQObjTotal"] = ck["object_properties"]
    m["CQCovClass"], m["CQClassTotal"] = ck["classes"]
    m["CQCovData"], m["CQDataTotal"] = ck["datatype_properties"]
    bc = cq["by_category"]
    for cat in ("lookup", "integrity", "reasoning", "requirement", "provenance"):
        m["CQ" + cat.capitalize()] = bc.get(cat, [0, 0])[1]

    reg = load("regression_results.json")
    rows = reg["rows"]
    for suite, tag in (("original-18", "Orig"), ("impact-4", "Imp"), ("targeted", "Targ")):
        sel = [r for r in rows if r["suite"] == suite]
        m[f"Reg{tag}Pass"], m[f"Reg{tag}Total"] = sum(r["pass"] for r in sel), len(sel)
    m["BaselineTrace"] = len(reg["baseline"]["trace"])
    nonacc = [r for r in rows if r.get("shacl_verdict") and r["observed"] in ("rejected", "pending_review")]
    m["RegNonAccepted"] = len(nonacc)
    m["RegNonAcceptedShaclOK"] = sum(r["shacl_verdict"] != "non-conforming" for r in nonacc)

    ev = load("evaluation_summary.json")
    run1 = load("evaluation_summary_run1.json")
    c = ev["corpus"]
    m["NumMutants"] = c["mutants"]
    m["NumPairs"] = f"{c['pairs']:,}"
    m["NumReqs"] = len(ev["requirements"])
    m["NumOps"] = len(c["by_operator"])
    m["MutChanging"] = c["mutants_changing_some_decision"]
    m["MutChangingPct"] = pct(c["mutants_changing_some_decision"] / c["mutants"])
    m["DecisionChanges"] = c["decision_changes"]
    m["DiffAgree"] = f"{ev['differential']['agreements']:,}"
    m["DiffInitialDis"] = run1["differential"]["n_disagreements"]
    m["DiffInitialMut"] = len({d["mutant"] for d in run1["differential"]["disagreements"]})
    m["DiffInitialPairs"] = f"{run1['differential']['pairs']:,}"
    m["DiffInitialMutants"] = run1["corpus"]["mutants"]
    for b, tag in (("shacl_global", "Glob"), ("shacl_focused", "Foc")):
        x = ev["baselines"][b]
        m[f"Shacl{tag}Agree"] = pct(x["agreement_broad"] / x["pairs"])
        m[f"Shacl{tag}FA"] = f"{x['false_acceptance']:,}"
        m[f"Shacl{tag}FR"] = f"{x['false_rejection']:,}"
        m[f"Shacl{tag}FAPct"] = pct(x["false_acceptance"] / x["pairs"])
        m[f"Shacl{tag}FRPct"] = pct(x["false_rejection"] / x["pairs"])
        conf = x["confusion"]
        exact = sum(v for k, v in conf.items() if k.split("|")[0] == k.split("|")[1])
        m[f"Shacl{tag}AgreeExact"] = pct(exact / x["pairs"])
        for st, nm_ in (("rejected", "Rej"), ("pending_review", "Rev"), ("conditional", "Cond"), ("not_derived", "ND")):
            m[f"Shacl{tag}FA{nm_}"] = f"{conf.get('accepted|' + st, 0):,}"
    imp = ev["impact"]
    m["GoldAssess"] = f"{imp['assessment']['_gold_pairs']:,}"
    m["GoldDecision"] = imp["decision"]["_gold_pairs"]
    names = {"M1_fine_trace_touched_diff": "One", "M2_fine_trace_subject_diff": "Two",
             "M3_coarse_trace_subject_diff": "Three", "M4_coarse_trace_transitive_closure": "Four",
             "M5_document_IR_tau_0.10": "Five", "M6_revalidate_all": "Six"}
    for k, t in names.items():
        a = imp["assessment"][k]
        m[f"Imp{t}P"], m[f"Imp{t}R"], m[f"Imp{t}Cost"] = f2(a["precision"]), f2(a["recall"]), f"{a['mean_revalidations']:.2f}"
        m[f"Imp{t}Miss"] = pct(1 - a["recall"], 0)
    m["ImpOneSaving"] = pct(1 - imp["assessment"]["M1_fine_trace_touched_diff"]["mean_revalidations"] / 10, 0)
    iso = load("record_isolation.json")
    assert iso["pass"]
    m["RecIsoAdded"], m["RecIsoRawTouched"] = iso["added_triples"], len(iso["raw_diff_touched_environment_identifiers"])
    irs = load("ir_sensitivity.json")
    miss = [v["miss_rate"] for v in irs["assessment"].values()]
    m["IRSensMissMin"], m["IRSensMissMax"] = pct(min(miss), 0), pct(max(miss), 0)
    lo = irs["assessment"]["0.05"]
    m["IRSensLowR"], m["IRSensLowCost"] = f2(lo["recall"]), f"{lo['mean_revalidations']:.2f}"
    m["IRSensLowMiss"] = pct(lo["miss_rate"], 0)
    m["SoundMissed"] = ev["trace_sufficiency"]["missed_by_touched_trace"]
    tr = ev["trace_relevance"]["methods"]
    m["RelevantPairs"] = ev["trace_relevance"]["relevant_pairs"]
    for k, t in (("recorded_fine_trace", "Fine"), ("coarse_trace", "Coarse")):
        m[f"Tr{t}P"], m[f"Tr{t}R"], m[f"Tr{t}F"] = f2(tr[k]["precision"]), f2(tr[k]["recall"]), f2(tr[k]["f1"])
    ir = {k: v for k, v in tr.items() if k.startswith("IR_")}
    best = max(ir, key=lambda k: ir[k]["f1"] or 0)
    m["TrIRBestTau"] = best.rsplit("_", 1)[-1]
    m["TrIRP"], m["TrIRR"], m["TrIRF"] = f2(ir[best]["precision"]), f2(ir[best]["recall"]), f2(ir[best]["f1"])
    ov = ev["overhead"]
    m["EnvTriples"] = ov["environment_triples"]
    m["EnvElements"] = ov["environment_elements_seven_views"]
    m["AuxElements"] = ov["auxiliary_elements"]
    m["AnnMean"] = f"{ov['annotation_triples_per_requirement']['mean']:.1f}"
    m["AnnMin"], m["AnnMax"] = ov["annotation_triples_per_requirement"]["min"], ov["annotation_triples_per_requirement"]["max"]
    m["RefsMean"] = f"{ov['references_per_requirement']['mean']:.1f}"
    m["TraceMean"] = f"{ov['trace_size']['mean']:.1f}"
    m["TraceMin"], m["TraceMax"] = ov["trace_size"]["min"], ov["trace_size"]["max"]
    m["ValidateMs"] = f"{ov['mean_validate_ms_per_requirement']:.2f}"

    mig = load("migration_results.json")["cases"]
    for k, t in (("rename_C002", "Ren"), ("split_D002", "Split"), ("merge_pharmacist_actions", "Merge")):
        x = mig[k]
        n = len(x["rows"])
        m[f"Mig{t}Preserved"] = f"{x['decisions_preserved_identity_aware']}/{n}"
        m[f"Mig{t}Naive"] = x["decisions_changed_naive"]
        m[f"Mig{t}Migrated"] = len(x["requirements_with_migrated_references"])
        m[f"Mig{t}Missed"] = len(x["missed_by_impact_query"])
        m[f"Mig{t}Selected"] = len(x["selected"])
        m[f"Mig{t}Ambiguous"] = len(x["ambiguous"])

    ex = load("extension_results.json")
    m["ExtCases"], m["ExtCQ"] = ex["regression_cases"], ex["cq_total"]
    m["ExtChanged"] = len(ex["regression_changed_by_vocabulary"]) + len(ex["cq_changed_by_vocabulary"])
    vd = load("view_derivation.json")
    m["VDFrameworks"] = vd["frameworks"]
    m["VDConcerns"] = len(vd["concerns"])

    # LLM-based independent evaluation (evaluation/llm-evaluation, studies E1-E3).
    llm = json.loads((ROOT / "evaluation" / "llm-evaluation" / "results" / "llm_evaluation_summary.json")
                     .read_text(encoding="utf-8"))
    m["LLMAgents"], m["LLMToolCalls"], m["LLMViolations"] = llm["agents"], llm["tool_calls"], llm["blinding_violations"]
    m["LLMFrozen"] = llm["frozen_files"]
    t1 = llm["e1"]["totals"]
    m["EOneAuthors"] = len(llm["e1"]["authors"])
    m["EOneScen"], m["EOneNewReq"], m["EOneExp"] = t1["scenarios"], t1["new_requirements"], t1["expectations"]
    m["EOneNontriv"], m["EOneMatchInit"], m["EOneMatchFinal"] = t1["nontrivial"], t1["matches_initial"], t1["matches_final"]
    m["EOneCQ"], m["EOneCQMatch"], m["EOneInvalid"] = t1["cqs"], t1["cqs_match"], t1["invalid"]
    m["EOneCQTerms"] = llm["e1"]["cq_reo_terms"]
    e2 = llm["e2"]
    m["ETwoCases"], m["ETwoPairs"], m["ETwoChanging"], m["ETwoRuns"] = e2["cases"], e2["pairs"], e2["changing_pairs"], e2["runs"]
    accs = [a["decision_accuracy"] for a in e2["analysts"]]
    m["ETwoAccMin"], m["ETwoAccMax"] = f"{min(accs):.3f}", f"{max(accs):.3f}"
    m["ETwoAmbRuns"], m["ETwoOtherErr"] = e2["ambiguous_item_runs"], e2["errors_outside_ambiguous_item"]
    m["ETwoRunSame"], m["ETwoRunPairs"] = e2["run_to_run_identical"], e2["run_to_run_pairs"]
    spd = [a["seconds_per_decision"] for a in e2["analysts"]]
    m["ETwoSecMin"], m["ETwoSecMax"] = f"{min(spd):.2f}", f"{max(spd):.2f}"
    ratio = min(spd) * 1000 / ov["mean_validate_ms_per_requirement"]
    m["ETwoSpeedup"] = f"{int(round(ratio, -2)):,}"
    e3 = llm["e3"]; pw = e3["pairwise"]
    m["EThreeCells"] = e3["cells"]
    m["EThreeKappaAOne"], m["EThreeKappaATwo"], m["EThreeKappaBB"] = (f"{pw[k]['cohen_kappa']:.2f}" for k in
                                                                      ("author~B1", "author~B2", "B1~B2"))
    m["EThreeWKappaAOne"], m["EThreeWKappaATwo"], m["EThreeWKappaBB"] = (f"{pw[k]['weighted_kappa_quadratic']:.2f}" for k in
                                                                         ("author~B1", "author~B2", "B1~B2"))
    m["EThreeAgreeAOne"], m["EThreeAgreeATwo"], m["EThreeAgreeBB"] = (pct(pw[k]["exact_agreement"], 0) for k in
                                                                      ("author~B1", "author~B2", "B1~B2"))
    m["EThreeFleiss"] = f"{e3['fleiss_kappa']:.2f}"
    dis = [pw[k]["disagreements"] for k in ("author~B1", "author~B2")]
    m["EThreeDis"] = sum(sum(d.values()) for d in dis)
    m["EThreeDisZeroOne"] = sum(d["0-1"] for d in dis)
    m["EThreeDisZeroTwo"] = sum(d["0-2"] for d in dis)
    m["ETwoSpeedupMax"] = f"{int(round(max(spd) * 1000 / ov['mean_validate_ms_per_requirement'], -2)):,}"
    tt = []
    for a in llm["e1"]["authors"]:
        model = a["model"].replace("claude-", "").replace("-5-5", " 5.5").capitalize()
        tt.append(f"{a['author']} & {model} & {a['scenarios']} & {a['new_requirements']} & {a['expectations']} & "
                  f"{a['nontrivial']} & {a['matches_initial']} & {a['matches_final']} & {a['cqs_match']}/{a['cqs']} \\\\")
    (GEN / "tab_llm_e1.tex").write_text("\n".join(tt) + "\n", encoding="utf-8")
    tt = []
    for a in sorted(e2["analysts"], key=lambda a: (a["condition"], a["model"], a["analyst"].endswith("r"))):
        model = a["model"].replace("claude-", "").replace("-5-5", " 5.5").capitalize()
        run = "2" if a["analyst"].endswith("r") else "1"
        tt.append(f"{a['condition']} & {model} & {run} & {a['correct']}/{a['pairs']} & {a['impact']['precision']:.2f} & "
                  f"{a['impact']['recall']:.2f} & {a['cases_without_error']}/{e2['cases']} & {a['seconds_per_decision']:.2f} \\\\")
    (GEN / "tab_llm_e2.tex").write_text("\n".join(tt) + "\n", encoding="utf-8")
    llm_fc = e3["first_class"]

    lines = ["% Generated by scripts/export_paper_macros.py -- do not edit by hand."]
    for k, v in sorted(m.items()):
        lines.append(f"\\newcommand{{\\{k}}}{{{v}}}")
    (GEN / "results_macros.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- tables -------------------------------------------------------------
    label = {"M1_fine_trace_touched_diff": "Read-set trace + touched-identifier diff (this work)",
             "M2_fine_trace_subject_diff": "Read-set trace + modified-subject diff",
             "M3_coarse_trace_subject_diff": "View-level trace + modified-subject diff (v1.0.0 rule)",
             "M4_coarse_trace_transitive_closure": "View-level trace + transitive dependency closure",
             "M5_document_IR_tau_0.10": "Document baseline: TF-IDF links ($\\tau=0.10$)",
             "M6_revalidate_all": "Re-validate every requirement"}
    t = []
    for k, lab in label.items():
        a, d = imp["assessment"][k], imp["decision"][k]
        t.append(f"{lab} & {f2(a['precision'])} & {f2(a['recall'])} & {f2(d['precision'])} & {f2(d['recall'])} & {a['mean_revalidations']:.2f} \\\\")
        if k == "M5_document_IR_tau_0.10":
            a5, d5 = irs["assessment"]["0.05"], irs["decision"]["0.05"]
            t.append(f"Document baseline: TF-IDF links ($\\tau=0.05$, most permissive) & {f2(a5['precision'])} & "
                     f"{f2(a5['recall'])} & {f2(d5['precision'])} & {f2(d5['recall'])} & {a5['mean_revalidations']:.2f} \\\\")
    (GEN / "tab_impact.tex").write_text("\n".join(t) + "\n", encoding="utf-8")
    t = []
    for k, lab in (("recorded_fine_trace", "Recorded read-set trace (this work)"),
                   ("coarse_trace", "View-level trace (identifiers of the seven views only)")):
        t.append(f"{lab} & {f2(tr[k]['precision'])} & {f2(tr[k]['recall'])} & {f2(tr[k]['f1'])} \\\\")
    for k in sorted(ir):
        tau = k.rsplit("_", 1)[-1]
        t.append(f"TF-IDF document links, $\\tau={tau}$ & {f2(ir[k]['precision'])} & {f2(ir[k]['recall'])} & {f2(ir[k]['f1'])} \\\\")
    (GEN / "tab_trace.tex").write_text("\n".join(t) + "\n", encoding="utf-8")
    t = []
    ops_desc = {"DEL-T": "delete one asserted triple", "DEL-E": "delete an element's description",
                "ENUM": "replace an enumerated value (SHACL \\texttt{sh:in})", "AUTH": "replace an authority value",
                "DUP": "add a conflicting second value", "RETARGET": "redirect a link within the same view",
                "ADD-LINK": "add a link allowed by domain/range", "NEW-RULE": "add a hard rule without validator",
                "NEW-UNC": "add an unvalidated uncertainty"}
    for op, n in c["by_operator"].items():
        ch = c["by_operator_changing"][op][0]
        t.append(f"\\texttt{{{op}}} & {ops_desc[op]} & {n} & {ch} \\\\")
    (GEN / "tab_operators.tex").write_text("\n".join(t) + "\n", encoding="utf-8")
    t = []
    nice = {"accepted": "acc", "accepted_with_reservations": "acc-res", "conditional": "cond",
            "pending_review": "review", "rejected": "rej", "not_derived": "n/d"}
    for b, lab in (("shacl_global", "Global"), ("shacl_focused", "Focused")):
        conf = ev["baselines"][b]["confusion"]
        for bv in ("accepted", "conditional", "rejected"):
            cells = [str(conf.get(f"{bv}|{cv}", 0)) for cv in nice]
            t.append(f"{lab if bv == 'accepted' else ''} & {nice[bv]} & " + " & ".join(cells) + " \\\\")
        t.append("\\midrule")
    (GEN / "tab_shacl_confusion.tex").write_text("\n".join(t[:-1]) + "\n", encoding="utf-8")
    t = []
    for k, lab in (("rename_C002", "Rename \\texttt{C002\\_FDA}"), ("split_D002", "Split \\texttt{D002\\_Patient} into two concepts"),
                   ("merge_pharmacist_actions", "Merge two Pharmacist actions")):
        x = mig[k]; n = len(x["rows"])
        t.append(f"{lab} & {len(x['selected'])} & {len(x['requirements_with_migrated_references'])} & "
                 f"{len(x['missed_by_impact_query'])} & {x['decisions_changed_naive']} & "
                 f"{x['decisions_preserved_identity_aware']}/{n} & {len(x['ambiguous'])} \\\\")
    (GEN / "tab_migration.tex").write_text("\n".join(t) + "\n", encoding="utf-8")
    t = []
    pretty = {"domain_entity": "domain entity", "domain_property": "domain property / assumption"}
    for cname, v in vd["concerns"].items():
        dec = v["decision"].replace("_", "\\_").replace("->", "$\\rightarrow$")
        fc = llm_fc[cname]
        t.append(f"{pretty.get(cname, cname)} & {v['first_class']} & {v['partial']} & {fc['B1']}/{fc['B2']} & "
                 f"{'yes' if v['C1'] else 'no'} & {'yes' if v['C2'] else 'no'} & "
                 f"{'yes' if v['C3_holds'] else 'no'} & {'yes' if v['C4'] else 'no'} & {dec} \\\\")
    (GEN / "tab_views.tex").write_text("\n".join(t) + "\n", encoding="utf-8")
    # Vocabulary tables from the generated inventory.
    import csv as _csv
    inv = list(_csv.DictReader(open(GEN / "reo_inventory.csv", encoding="utf-8")))
    esc = lambda s: s.replace("reo:", "").replace("_", "\\_")
    rows_o = [r for r in inv if r["kind"] == "Object property"]
    t = [f"{esc(r['domain_or_parent'])} & \\texttt{{{esc(r['element'])}}} & {esc(r['range'])} & {r['module']} \\\\"
         for r in sorted(rows_o, key=lambda r: (r["module"], r["domain_or_parent"], r["element"]))]
    (GEN / "tab_objprops.tex").write_text("\n".join(t) + "\n", encoding="utf-8")
    groups = {}
    for r in inv:
        if r["kind"] == "Datatype property":
            groups.setdefault((r["module"], r["domain_or_parent"]), []).append(
                esc(r["element"]) + ("" if r["range"] == "xsd:string" else f" ({esc(r['range']).replace('xsd:', '')})"))
    t = [f"{esc(d)} ({len(v)}) & {', '.join(sorted(v))} \\\\" for (mod, d), v in sorted(groups.items())]
    (GEN / "tab_dataprops.tex").write_text("\n".join(t) + "\n", encoding="utf-8")
    # Requirement set with decisions, trace sizes and the deciding reason.
    import sys as _sys
    _sys.path.insert(0, str(ROOT))
    import reo_checker as R
    ex_dir = ROOT / "examples" / "medical-emergency"
    env = R.project(R.load_graph([ex_dir / "hospital.ttl", ex_dir / "hospital-extension.ttl"]))
    reqs = R.load_requirements(R.load_graph([ex_dir / "hospital-requirements.ttl"]))
    nice = {"accepted": "accepted", "accepted_with_reservations": "acc.\\ w/ reservations", "conditional": "conditional",
            "pending_review": "pending review", "rejected": "rejected", "not_derived": "not derived"}
    t = []
    for q in reqs:
        r = R.validate(env, q)
        want = {"rejected": ("FAIL [hard]",), "pending_review": ("UNCHECKED [hard]",), "conditional": ("OPEN",),
                "accepted_with_reservations": ("FAIL [soft]", "UNCHECKED [soft]")}.get(r.state, ())
        reason = next((j for j in r.justifications if j.startswith(want)), "all obligations hold") if want \
            else "all obligations hold"
        reason = reason.split(": ", 1)[-1]
        reason = (reason.replace("_", "\\_").replace("->", "$\\rightarrow$").replace("'", "")
                  .replace("[", "").replace("]", ""))
        ctx = q.context.split("_")[0]
        t.append(f"{q.rid} & {q.seed_goal} & {ctx} & {nice[r.state]} & {len(r.trace)} & {reason} \\\\")
    (GEN / "tab_requirements.tex").write_text("\n".join(t) + "\n", encoding="utf-8")
    print(f"{len(m)} macros; tables written to {GEN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
