#!/usr/bin/env python3
"""Build the specification pack given to LLM evaluators.

The pack contains only published material: the contract text of the paper
(Sections III-C..III-F, IV-B..IV-C, V, VII, converted from LaTeX), the ontology
modules, and the example files. It deliberately excludes reo_checker.py,
sparql_oracle.py, every test suite and every result file, and the view-coding
matrix (which is coded independently in study E3).

Usage: python build_spec.py <paper/access.tex> <out_dir>
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / "generated"

KEEP = [  # (start label/marker, end label/marker) on section boundaries, end exclusive
    (r"\section{Foundations", r"\subsection{Deriving the seven views}"),
    (r"\subsection{Overlaps and role separation}", r"Table~\ref{tab:metamodels} compares"),
    (r"\subsection{Extension contract}", r"\section{REO: The RE-Environment Ontology}"),
    (r"\subsection{Classes and predicates}", r"\section{Architecture and Implementation Boundary}"),
    (r"\section{Worked Example", r"\section{Evaluation}"),
]


def macros():
    vals = {}
    for m in re.finditer(r"\\newcommand\{\\(\w+)\}\{([^}]*)\}", (GEN / "results_macros.tex").read_text()):
        vals[m.group(1)] = m.group(2)
    return vals


def fix_table(m):
    rows = m.group(2)
    header = next(l for l in rows.splitlines() if "&" in l)
    n = header.count("&") + 1
    return r"\begin{tabular}{" + "l" * n + "}\n" + rows + r"\end{tabular}"


def fix_alg(m):
    lines, depth = [], 0
    for tok in re.split(r"(?=\\(?:STATE|IF|ENDIF|FORALL|ENDFOR|RETURN|REQUIRE|ENSURE|COMMENT)\b)", m.group(1)):
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith((r"\ENDIF", r"\ENDFOR")):
            depth -= 1; tok = tok.split(None, 1)[1] if " " in tok else ""
            if not tok:
                continue
        opens = tok.startswith((r"\IF", r"\FORALL"))
        for k, v in ((r"\STATE", ""), (r"\IF", "if"), (r"\FORALL", "for all"), (r"\RETURN", "return"),
                     (r"\REQUIRE", "input:"), (r"\ENSURE", "output:"), (r"\COMMENT", "  // "), (r"\OR", "or")):
            tok = tok.replace(k, v)
        tok = tok.replace(r"\ENDIF", "").replace("~", " ").strip()
        lines.append("  " * depth + tok)
        if opens:
            depth += 1
    return "\\begin{verbatim}\n" + "\n".join(lines) + "\n\\end{verbatim}"


def main(tex_path, out_dir):
    tex = Path(tex_path).read_text(encoding="utf-8")
    parts = []
    for a, b in KEEP:
        i = tex.index(a); j = tex.index(b, i)
        parts.append(tex[i:j])
    body = "\n".join(parts)
    body = re.sub(r"\\begin\{figure\*?\}.*?\\end\{figure\*?\}", "", body, flags=re.S)
    body = re.sub(r"Figures?~\\ref\{[^}]*\}( and~\\ref\{[^}]*\})?", "the figure", body)
    body = re.sub(r"\\tabinput\{([^}]*)\}", lambda m: (ROOT / m.group(1)).read_text(encoding="utf-8"), body)
    vals = macros()
    body = re.sub(r"\\(\w+)\{\}", lambda m: vals.get(m.group(1), m.group(0)), body)
    body = re.sub(r"\\(\w+)(?![\w{])", lambda m: vals.get(m.group(1), m.group(0)), body)
    body = body.replace(r"\botrule", r"\bottomrule")
    body = re.sub(r"\\begin\{tabular\*?\}(\{\\textwidth\})?\{[^\n]*\}\n(.*?)\\end\{tabular\*?\}", fix_table, body, flags=re.S)
    body = re.sub(r"\\begin\{algorithmic\}\[1\](.*?)\\end\{algorithmic\}", fix_alg, body, flags=re.S)
    body = re.sub(r"\\cite\{[^}]*\}", "", body)
    pre = (r"\newcommand{\Env}{\mathcal{E}}\newcommand{\Trace}{\mathsf{T}}\newcommand{\st}[1]{\textit{#1}}"
           r"\newcommand{\EE}{EE}\newcommand{\ECRE}{EC-RE}\newcommand{\REO}{REO}\newcommand{\fc}{$\bullet$}\newcommand{\pc}{$\circ$}")
    doc = pre + "\n\\begin{document}\n" + body + "\n\\end{document}\n"
    md = subprocess.run(["pandoc", "-f", "latex", "-t", "gfm", "--wrap=none"], input=doc,
                        capture_output=True, text=True, check=True).stdout
    md = re.sub(r'<a href="#([^"]+)"[^>]*>[^<]*</a>', r"[\1]", md)
    md = re.sub(r'<div id="([^"]+)">', r"**[\1]**", md)
    md = md.replace("</div>", "")
    md = re.sub(r'<div class="[^"]*">', "", md)
    md = re.sub(r'<span id="[^"]*" label="[^"]*"></span>\s*', "", md)
    md = re.sub(r"\|(\s+\|)+\s*$", "|", md, flags=re.M)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    head = ("# EC-RE specification (excerpt of the paper)\n\n"
            "This is the published specification of the REO vocabulary and of the derivation contract "
            "(paper Sections III, IV-B/C, V and VII). Machine-readable files in this folder: "
            "`reo-core.ttl`, `reo-derivation.ttl` (ontology modules), `hospital.ttl`, "
            "`hospital-extension.ttl` (example environment), `hospital-requirements.ttl` (ten annotated "
            "requirements). Decision state names used in answers: accepted, accepted_with_reservations, "
            "conditional, pending_review, rejected, not_derived.\n\n")
    (out / "SPEC.md").write_text(head + md, encoding="utf-8")
    for f in ["ontology/reo-core.ttl", "ontology/reo-derivation.ttl", "examples/medical-emergency/hospital.ttl",
              "examples/medical-emergency/hospital-extension.ttl", "examples/medical-emergency/hospital-requirements.ttl"]:
        shutil.copy(ROOT / f, out / Path(f).name)
    print(f"wrote {out} ({len(md)} chars of spec)")


if __name__ == "__main__":
    main(*sys.argv[1:])
