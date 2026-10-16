#!/usr/bin/env python3
"""Audit the tool logs of the LLM evaluator agents (blinding check).

For every agent transcript (JSON lines written by the agent runtime) it extracts
the serving model reported in each API response and every tool call with its
arguments, and flags any call that is not a Read inside the agent's own folder
or the one permitted Write. The extracted log (without file contents) is
written next to the frozen outputs, so the check can be repeated by readers.

Usage: python audit_transcripts.py <out.json> <sandbox_root> <transcript.jsonl> [...]
"""
import json
import sys
from pathlib import Path


def main(out, sandbox_root, *paths):
    report = []
    for p in paths:
        rows = [json.loads(l) for l in open(p, encoding="utf-8")]
        first = next(r for r in rows if r.get("type") == "user")
        prompt = first["message"]["content"]
        prompt = prompt if isinstance(prompt, str) else json.dumps(prompt)
        folder = next(w for w in prompt.replace("\n", " ").split() if w.startswith(sandbox_root)).rstrip(".")
        folder = folder.split("/TASK.md")[0].rstrip("/") + "/"
        models, calls, violations = set(), [], []
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                 "cache_creation_input_tokens": 0}
        for r in rows:
            if r.get("type") != "assistant":
                continue
            m = r["message"]
            if m.get("model"):
                models.add(m["model"])
            for k in usage:
                usage[k] += (m.get("usage") or {}).get(k, 0) or 0
            for c in m.get("content", []):
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    args = {k: v for k, v in c.get("input", {}).items() if k != "content"}
                    calls.append({"tool": c["name"], "args": args})
                    path = str(args.get("file_path", ""))
                    ok = (c["name"] == "Read" and path.startswith(folder)) or \
                         (c["name"] == "Write" and path.startswith(folder + "out/"))
                    if not ok:
                        violations.append({"tool": c["name"], "args": args})
        report.append({"transcript": Path(p).name, "folder": folder, "models": sorted(models),
                       "tool_calls": calls, "violations": violations, "usage": usage,
                       "started": rows[0].get("timestamp"), "ended": rows[-1].get("timestamp")})
    Path(out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    for a in report:
        print(f'{a["folder"]:45s} {",".join(a["models"]):18s} calls={len(a["tool_calls"])} violations={len(a["violations"])}')


if __name__ == "__main__":
    main(*sys.argv[1:])
