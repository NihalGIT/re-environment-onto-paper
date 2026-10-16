# Task E1 — independent authoring of test scenarios and competency questions

You act as an **independent evaluator** of the EC-RE derivation contract. You did not build the
reference checker and you must not try to obtain or reconstruct it. Work only from the files in the
`spec/` folder of your working folder:

* `SPEC.md` — the published specification (vocabulary, obligations O1–O9, decision policy,
  worked example with the decisions of R001–R010 on the unmodified example);
* `reo-core.ttl`, `reo-derivation.ttl` — ontology modules;
* `hospital.ttl`, `hospital-extension.ttl` — the example environment (the base for every scenario);
* `hospital-requirements.ttl` — ten annotated requirements R001–R010.

Rules: do not read, list or search any file outside your `spec/` folder; do not run code (no shell);
derive every expected value by applying the specification by hand. Your expectations are frozen
(hashed) before anyone executes them, and they are never edited afterwards — so state what the
**specification** implies, not what you guess an implementation does. If the specification is
ambiguous for an item, still give your best reading and say why in the rationale.

## Part A — 12 change scenarios

Each scenario is a change to the base environment (`hospital.ttl` + `hospital-extension.ttl`),
given as Turtle triples to remove and/or add, plus the expected decision state of **every**
requirement R001–R010 after the change (and of any requirement you add). Aim for diversity:

* together, the scenarios should exercise all of O1–O9 and all six decision states;
* include at least 2 scenarios that add a new requirement annotation (`add_requirements_turtle`,
  with `reo:requirementId` set, e.g. "RX01");
* include at least 2 scenarios on uncertainties (status, impact level, `blocks`/`affects`),
  2 on constraints (applicability, exceptions, validator keys, enforcement level),
  1 with conflicting values for an attribute the contract reads, and 2 whose change should leave
  most decisions unchanged;
* make removals match the base files exactly (same subject, predicate, object and literal form),
  otherwise the removal has no effect.

Predefined prefixes in all snippets (do not redeclare): `reo:`, `ex:`, `req:`
(`http://hospital.example.org/requirements#`), `rdf:`, `rdfs:`, `owl:`, `xsd:`.
State names: `accepted`, `accepted_with_reservations`, `conditional`, `pending_review`,
`rejected`, `not_derived`.

## Part B — 8 competency questions

Questions an RE analyst would ask of this environment model (look-up, integrity, reasoning,
requirement, provenance-of-decision categories). For each: the question in English, a SPARQL 1.1
query, and the expected answer. Queries run on the union of `reo-core.ttl`, `reo-derivation.ttl`,
`hospital.ttl`, `hospital-extension.ttl` and `hospital-requirements.ttl` with **no inference**
(use `rdfs:subClassOf*` paths when you need subclass closure). The same prefixes are predefined.
Answers are compared as sets of rows: IRIs by local name (text after `#`), literals by lexical
form; ASK queries as booleans.

## Output

Write a single JSON file to `out/suite.json` in your working folder, exactly in this shape:

```json
{
  "author_code": "<given in your instructions>",
  "self_reported_model": "<the exact model name/ID stated in your system environment>",
  "scenarios": [
    {"id": "S01", "description": "...", "remove_turtle": "...", "add_turtle": "...",
     "add_requirements_turtle": "", "obligations_targeted": ["O7"],
     "expected": {"R001": "conditional", "R002": "...", "...": "...", "R010": "..."},
     "rationale": "why, citing the specification"}
  ],
  "cqs": [
    {"id": "Q01", "category": "lookup", "question": "...", "kind": "select",
     "sparql": "SELECT ?x WHERE { ... }", "expected": [["Physician"], ["Pharmacist"]],
     "rationale": "..."},
    {"id": "Q02", "category": "integrity", "question": "...", "kind": "ask",
     "sparql": "ASK { ... }", "expected": false, "rationale": "..."}
  ]
}
```

The file must be valid JSON (escape newlines inside strings as `\n`). When done, reply with one
line: the number of scenarios and questions written.
