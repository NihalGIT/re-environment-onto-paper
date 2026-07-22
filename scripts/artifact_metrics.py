#!/usr/bin/env python3
"""Regenerate reproducible REO artifact metrics from the Turtle corpus."""

from __future__ import annotations

import json
from pathlib import Path

from rdflib import Graph, OWL, RDF, SH


def load_graph(path: Path) -> Graph:
    graph = Graph()
    graph.parse(path, format="turtle")
    return graph


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    turtle_files = sorted(
        list((repo_root / "ontology").glob("*.ttl"))
        + list((repo_root / "examples").glob("**/*.ttl"))
        + list((repo_root / "test-cases").glob("**/*.ttl"))
    )

    per_file: dict[str, int] = {}
    for path in turtle_files:
        graph = load_graph(path)
        per_file[path.relative_to(repo_root).as_posix()] = len(graph)

    core = load_graph(repo_root / "ontology" / "reo-core.ttl")
    shapes = load_graph(repo_root / "ontology" / "reo-shapes.ttl")

    metrics = {
        "reo_version": "1.0.0",
        "turtle_file_count": len(turtle_files),
        "total_triples": sum(per_file.values()),
        "triples_by_file": per_file,
        "core": {
            "triples": len(core),
            "owl_classes": len(set(core.subjects(RDF.type, OWL.Class))),
            "object_properties": len(
                set(core.subjects(RDF.type, OWL.ObjectProperty))
            ),
            "datatype_properties": len(
                set(core.subjects(RDF.type, OWL.DatatypeProperty))
            ),
            "owl_restrictions": len(
                set(core.subjects(RDF.type, OWL.Restriction))
            ),
        },
        "shapes": {
            "triples": len(shapes),
            "node_shapes": len(set(shapes.subjects(RDF.type, SH.NodeShape))),
            "property_paths": len(set(shapes.subjects(SH.path, None))),
            "sparql_constraints": len(set(shapes.objects(None, SH.sparql))),
        },
    }

    output = repo_root / "artifact_metrics.json"
    output.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"Turtle files : {metrics['turtle_file_count']}")
    print(f"Total triples: {metrics['total_triples']}")
    print(f"Results written: {output.name}")


if __name__ == "__main__":
    main()
