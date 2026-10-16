#!/usr/bin/env python3
"""Draw REO v1.1.0 class diagrams directly from the Turtle modules (Graphviz).

Every node, subclass list and edge is read from reo-core.ttl and
reo-derivation.ttl; nothing is drawn by hand. Two diagrams are produced:
figures/reo-core.pdf (core module) and figures/reo-derivation.pdf
(derivation module and the core classes it links to)."""
import subprocess
from collections import defaultdict
from pathlib import Path

from rdflib import OWL, RDF, RDFS, Graph, URIRef

ROOT = Path(__file__).resolve().parents[1]
REO = "http://re-environment-onto.org/ontology#"
g = Graph()
for f in ("reo-core.ttl", "reo-derivation.ttl"):
    g.parse(ROOT / "ontology" / f, format="turtle")
core = Graph().parse(ROOT / "ontology" / "reo-core.ttl", format="turtle")
own = lambda s: isinstance(s, URIRef) and str(s).startswith(REO)
nm = lambda s: str(s).split("#")[-1]
classes = {s for s in g.subjects(RDF.type, OWL.Class) if own(s)}
parent = {c: next((o for o in g.objects(c, RDFS.subClassOf) if own(o)), None) for c in classes}
top = sorted((c for c in classes if parent[c] is None), key=nm)
subs = defaultdict(list)
for c in classes:
    if parent[c] is not None:
        subs[parent[c]].append(nm(c))
dcount = defaultdict(int)
for p in g.subjects(RDF.type, OWL.DatatypeProperty):
    d = g.value(p, RDFS.domain)
    while d is not None and d not in top and parent.get(d) is not None:
        d = parent[d]
    if d is not None:
        dcount[d] += 1
DERIV = {"Requirement", "DerivationRecord", "ValidationActivity", "DecisionState"}
VIEWS = {"Actor": "A", "Goal": "G", "DomainConcept": "D", "Constraint": "C", "Context": "X",
         "Uncertainty": "U", "Interaction": "I"}
HEAD = ['digraph REO {',
        ' graph [rankdir=%s, nodesep=0.18, ranksep=0.3, splines=true, fontname="Helvetica", newrank=true];',
        ' node [shape=plain, fontname="Helvetica", fontsize=16];',
        ' edge [fontname="Helvetica", fontsize=14, arrowsize=0.7];']


def label(c, detailed=True):
    title = nm(c) + (f" ({VIEWS[nm(c)]})" if nm(c) in VIEWS else "")
    color = "#f2f2f2" if nm(c) in DERIV else ("#e8eef7" if nm(c) in VIEWS else "#ffffff")
    rows = [f'<tr><td bgcolor="{color}"><b>{title}</b></td></tr>']
    if detailed and subs[c]:
        s = sorted(subs[c])
        # one subclass per line keeps the boxes narrow, so the figure stays legible at column width
        rows.append('<tr><td align="left"><font point-size="14">' + "<br/>".join(s) + '</font></td></tr>')
    if detailed and dcount[c]:
        rows.append(f'<tr><td align="left"><font point-size="12.5" color="#444444">{dcount[c]} datatype properties</font></td></tr>')
    style = ' style="dashed"' if nm(c) in DERIV else ""
    return f'<<table border="1" cellborder="0" cellspacing="0" cellpadding="3"{style}>' + "".join(rows) + "</table>>"


def edges_of(graph):
    e = defaultdict(list)
    for p in sorted(graph.subjects(RDF.type, OWL.ObjectProperty), key=nm):
        if not own(p):
            continue
        d, r = g.value(p, RDFS.domain), g.value(p, RDFS.range)
        e[(nm(d) if d is not None and own(d) else "Any", nm(r) if r is not None and own(r) else "Any")].append(nm(p))
    return e


def render(name, rankdir, nodes, edges, extra=(), detailed_nodes=None):
    lines = [HEAD[0], HEAD[1] % rankdir] + HEAD[2:]
    for c in top:
        if nm(c) in nodes:
            lines.append(f' {nm(c)} [label={label(c, detailed_nodes is None or nm(c) in detailed_nodes)}];')
    if "Any" in nodes:
        lines.append(' Any [shape=box, style="rounded,dotted", fontsize=14, label="any element\\n(owl:Thing)"];')
    for (d, r), ps in sorted(edges.items()):
        style = ', style="dashed"' if d in DERIV else ""
        lab = "\\n".join(ps)
        lines.append(f' {d} -> {r} [label="{lab}"{style}];')
    lines += list(extra) + ["}"]
    out = ROOT / "figures"
    out.mkdir(exist_ok=True)
    (out / f"{name}.dot").write_text("\n".join(lines))
    subprocess.run(["dot", "-Tpdf", str(out / f"{name}.dot"), "-o", str(out / f"{name}.pdf")], check=True)
    subprocess.run(["dot", "-Tpng", "-Gdpi=90", str(out / f"{name}.dot"), "-o", str(out / f"{name}.png")], check=True)
    return sum(len(v) for v in edges.values())


core_edges = edges_of(core)
core_nodes = {nm(c) for c in top if nm(c) not in DERIV} | {"Any"}
n1 = render("reo-core", "LR", core_nodes, core_edges)
all_edges = edges_of(g)
der_edges = {k: v for k, v in all_edges.items() if k[0] in DERIV}
der_nodes = {x for k in der_edges for x in k}
n2 = render("reo-derivation", "LR", der_nodes, der_edges,
            extra=[' DerivationRecord -> ValidationActivity [label="prov:wasGeneratedBy", style="dashed"];'],
            detailed_nodes=DERIV)
print("core edges:", n1, "derivation edges:", n2 + 1)
