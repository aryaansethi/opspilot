"""Validate a dataset version: every label must be checkable against the corpus.

Checks: unique ids and question texts; every relevant (document, section) exists and
has body text (so it can be retrieved); every expected fact appears verbatim
(case-insensitive) in the union of the question's relevant sections; answerable is
consistent with `relevant`; match is "all" or "any"; ambiguous questions use "any".
Exit code 1 on any problem.

Usage: python evaluation/datasets/validate.py v2
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def sections(md: str) -> dict[str, str]:
    """heading -> heading line + body text up to the next heading (any level)."""
    out: dict[str, str] = {}
    current, buf = None, []
    for line in md.splitlines():
        m = HEADING.match(line)
        if m:
            if current is not None:
                out[current] = "\n".join(buf)
            current, buf = m.group(2), [m.group(2)]
        elif current is not None:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf)
    return out


def validate(version: str) -> list[str]:
    base = ROOT / version
    corpus = {p.stem: sections(p.read_text()) for p in (base / "corpus").glob("*.md")}
    qs = [json.loads(line) for line in (base / "questions.jsonl").read_text().splitlines() if line.strip()]
    problems = []
    for field in ("id", "question"):
        dupes = [k for k, n in Counter(q[field] for q in qs).items() if n > 1]
        if dupes:
            problems.append(f"duplicate {field}: {dupes}")
    for q in qs:
        rel = q["relevant"]
        if q["answerable"] != bool(rel):
            problems.append(f"{q['id']}: answerable={q['answerable']} but {len(rel)} relevant sections")
        match = q.get("match", "all")
        if match not in ("all", "any"):
            problems.append(f"{q['id']}: match must be all|any")
        if q["kind"] == "ambiguous" and match != "any":
            problems.append(f"{q['id']}: ambiguous questions must use match=any")
        texts = []
        for r in rel:
            secs = corpus.get(r["document"])
            if secs is None:
                problems.append(f"{q['id']}: unknown document {r['document']}")
                continue
            body = secs.get(r["section"])
            if body is None:
                problems.append(f"{q['id']}: no section '{r['section']}' in {r['document']}")
                continue
            if not body.split("\n", 1)[-1].strip():
                problems.append(f"{q['id']}: section '{r['section']}' in {r['document']} has no body text")
            texts.append(body.lower())
        joined = "\n".join(texts)
        for fact in q.get("expected_facts", []):
            if fact.lower() not in joined:
                problems.append(f"{q['id']}: fact {fact!r} not found in its relevant sections")
    return problems


def main() -> int:
    version = sys.argv[1] if len(sys.argv) > 1 else "v2"
    problems = validate(version)
    qs = [json.loads(line) for line in (ROOT / version / "questions.jsonl").read_text().splitlines() if line.strip()]
    print(f"{version}: {len(qs)} questions, kinds {dict(Counter(q['kind'] for q in qs))}, "
          f"topics {dict(Counter(q.get('topic', '-') for q in qs))}, splits {dict(Counter(q['split'] for q in qs))}")
    for p in problems:
        print("PROBLEM:", p)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
