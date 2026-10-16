# Task E3 — independent coding of RE frameworks against candidate environment concerns

You are an independent coder. For each of the 12 frameworks below, score each of the 17 candidate
concerns according to how the framework, **as defined in the cited primary sources**, represents it.
Work from your own knowledge of these sources. Do not read, list or search any file on this
machine other than this task file; do not use web search; do not run code. You will not see any
other coding before you finish.

## Scores
* **2 — first-class**: the framework has a dedicated modelling construct for the concern (a named
  element type, relation type or notation symbol with its own definition).
* **1 — partial**: the concern appears only as an attribute of another construct, a secondary or
  optional construct, an annotation, or a textual item/guideline.
* **0 — absent**: the concern is not represented.

## Frameworks (primary sources)
1. **WRSPM** — reference model for requirements and specifications: Zave & Jackson, "Four dark
   corners of requirements engineering", ACM TOSEM 1997; Gunter, Gunter, Jackson & Zave, "A reference
   model for requirements and specifications", IEEE Software 2000.
2. **Problem Frames** — Jackson, *Problem Frames*, Addison-Wesley 2001.
3. **KAOS** — Dardenne, van Lamsweerde & Fickas, "Goal-directed requirements acquisition", SCP 1993;
   van Lamsweerde, "Goal-oriented RE: a guided tour", RE 2001; van Lamsweerde & Letier, "Handling
   obstacles in goal-oriented RE", IEEE TSE 2000.
4. **i\* / iStar 2.0** — Yu, "Towards modelling and reasoning support for early-phase RE", RE 1997;
   Dalpiaz, Franch & Horkoff, "iStar 2.0 language guide", 2016.
5. **CORE ontology for RE** — Jureta, Mylopoulos & Faulkner, "Revisiting the core ontology and
   problem in requirements engineering", RE 2008.
6. **Context (Dey)** — Dey, "Understanding and using context", Personal and Ubiquitous Computing 2001.
7. **Contextual goal models** — Ali, Dalpiaz & Giorgini, "A goal-based framework for contextual
   requirements modeling and analysis", RE Journal 2010.
8. **Uncertainty taxonomy** — Ramirez, Jensen & Cheng, "A taxonomy of uncertainty for dynamically
   adaptive systems", SEAMS 2012.
9. **RELAX** — Whittle, Sawyer, Bencomo, Cheng & Bruel, "RELAX: incorporating uncertainty into the
   specification of self-adaptive systems", RE 2009.
10. **ISO/IEC/IEEE 29148** — Systems and software engineering — Life cycle processes — Requirements
    engineering (2018).
11. **SysML v2 requirements** — OMG Systems Modeling Language v2 (requirement definitions and usages).
12. **Traceability reference model** — Ramesh & Jarke, "Toward reference models for requirements
    traceability", IEEE TSE 2001.

## Candidate concerns
| Key | Meaning |
|---|---|
| actor | an active entity (person, role, organisation, software or hardware system) that performs behaviour or is responsible for something |
| stakeholder | a party with an interest in the system or its goals, distinguished from entities that act |
| goal | an objective or intention the system and its environment should achieve |
| quality | a quality attribute or non-functional property (performance, security, usability, ...) |
| domain_entity | a thing, object, data entity or phenomenon of the application domain that requirements refer to |
| domain_property | an attribute of a domain entity, or an indicative property/assumption that holds in the domain |
| constraint | a rule that restricts permitted behaviour or solutions (regulation, policy, design constraint) |
| context | the situation or circumstances in which the system operates or a requirement applies |
| time | temporal aspects modelled explicitly (time points, intervals, deadlines, temporal operators) |
| location | spatial aspects (place, position, region) |
| uncertainty | explicitly modelled lack of knowledge, assumptions that may not hold, or unknown variability |
| interaction | an exchange of phenomena, information or dependencies between entities |
| action | an operation, task or activity that an entity can perform |
| resource | an entity that is used or consumed to perform tasks |
| process | ordered behaviour: workflows, sequences of activities, state machines |
| event | an occurrence at a point in time that may trigger behaviour |
| provenance | recording of the origin, rationale, history or trace links of requirements and model elements |

## Output
Write `out/coding.json` in your working folder:

```json
{"coder_code": "<given in your instructions>",
 "self_reported_model": "<exact model name/ID stated in your system environment>",
 "matrix": {"WRSPM": {"actor": 0, "stakeholder": 0, "...": 0},
            "Problem Frames": {"...": 0}},
 "notes": {"WRSPM": "one or two sentences naming the constructs that justify the 2s and 1s"}}
```

Use exactly the 12 framework names WRSPM, Problem Frames, KAOS, iStar, CORE, Dey, Contextual goal
models, Uncertainty taxonomy, RELAX, ISO 29148, SysML v2, Traceability reference model, and the 17
concern keys above. Reply with one line when done.
