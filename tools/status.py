#!/usr/bin/env python3
"""Set every status line from the test reports, so no status is typed by hand.

- recipes/<ID>/build-spec.md: the n8n row of the status table.
- recipes/<ID>/prompts/*.md: the "Status:" line.
- README.md: the "n8n build" column of the recipe index.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def report(d: Path):
    p = d / "n8n" / "test-report.md"
    if not p.exists():
        return None
    t = p.read_text()
    date = re.search(r"Run (\d{4}-\d{2}-\d{2}) on n8n ([\d.]+)", t)
    res = re.search(r"Result: (\d+) of (\d+) cases passed", t)
    if not (date and res):
        return None
    return {"date": date.group(1), "n8n": date.group(2), "passed": int(res.group(1)), "total": int(res.group(2))}


def main() -> None:
    readme = (ROOT / "README.md").read_text()
    for d in sorted((ROOT / "recipes").iterdir()):
        r = report(d)
        ok = r and r["passed"] == r["total"]
        cell = (f"Available: golden set passed on n8n {r['n8n']}, {r['date']} ([report](n8n/test-report.md))" if ok else
                f"Available: {r['passed']} of {r['total']} golden-set cases passed on n8n {r['n8n']}, {r['date']} ([report](n8n/test-report.md))" if r else
                "Not yet available")
        spec = d / "build-spec.md"
        s = re.sub(r"^\| n8n \|[^\n]*$", f"| n8n | [`n8n/workflow.json`](n8n/workflow.json) | {cell} |", spec.read_text(), count=1, flags=re.M)
        spec.write_text(s)
        for pf in (d / "prompts").glob("*.md") if (d / "prompts").is_dir() else []:
            line = (f"Status: run against the golden set in the n8n build on Claude Haiku 5.5, {r['date']} ([report](../n8n/test-report.md))."
                    if ok else "Status: draft; not yet run against the golden set.")
            pf.write_text(re.sub(r"^Status: [^\n]*$", line, pf.read_text(), count=1, flags=re.M))
        col = (f"[Tested {r['date']}](recipes/{d.name}/n8n/test-report.md)" if ok else "Not yet available")
        readme = re.sub(rf"^(\| \[{re.escape(d.name)}\][^\n]*\| )[^|\n]*( \|)$", lambda m: m.group(1) + col + m.group(2), readme, count=1, flags=re.M)
    (ROOT / "README.md").write_text(readme)
    print("statuses updated")


if __name__ == "__main__":
    main()
