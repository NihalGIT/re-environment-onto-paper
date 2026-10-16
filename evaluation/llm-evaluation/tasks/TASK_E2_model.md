# Task E2 — re-assessing requirements after environment changes (model-based, no checker)

You are a requirements analyst. The `spec/` folder of your working folder contains:

* `SPEC.md` — the decision policy (obligations O1–O9 and the ordered decision states);
* `reo-core.ttl`, `reo-derivation.ttl` — the REO ontology modules;
* `hospital.ttl`, `hospital-extension.ttl` — the environment model (REO, Turtle);
* `hospital-requirements.ttl` — the ten requirements R001–R010 with their explicit annotations;
* `base_decisions.md` — the decision of each requirement on the unmodified model;
* `changes.json` — 20 independent change cases. Each case gives Turtle triples removed from and/or
  added to the **unmodified** model (prefixes `reo:` and `ex:` as in the model; cases do not
  accumulate).

For every case, decide the state of **each** of R001–R010 after the change, by applying the policy
of `SPEC.md` by hand to the model and the annotations.

Rules: do not read, list or search any file outside your `spec/` folder; do not run code (no shell).

Write `out/answers.json` in your working folder:

```json
{"analyst_code": "<given in your instructions>",
 "self_reported_model": "<exact model name/ID stated in your system environment>",
 "answers": [{"case": "C01",
              "decisions": {"R001": "conditional", "R002": "...", "...": "...", "R010": "..."},
              "note": "one short sentence"}]}
```

State names: `accepted`, `accepted_with_reservations`, `conditional`, `pending_review`, `rejected`,
`not_derived`. Give all 20 cases and all ten requirements per case. Reply with one line when done.
