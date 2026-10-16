# Adjudication task

You adjudicate disagreements between an expected decision (written by an evaluator from the
specification) and the decision produced by the reference implementation. Read `spec/SPEC.md` and
the Turtle files in `spec/`, then `items.json`. For each item decide which statement is true:

* **A** — the evaluator misapplied the specification (the implementation follows it);
* **B** — the implementation deviates from the specification (the evaluator follows it);
* **C** — the specification is ambiguous or underspecified on this point (both readings defensible);
* **D** — the disagreement comes from the test harness or the encoding, not from either reading.

Rules: read only files inside your working folder; do not run code; do not search the web.
Write `out/adjudication.json`: `[{"item": "...", "verdict": "A|B|C|D", "spec_passages": ["quoted
sentence(s) that decide it"], "reasoning": "...", "suggested_fix": "..."}]`.
Also put `"self_reported_model"` in each entry. Reply with one line when done.
