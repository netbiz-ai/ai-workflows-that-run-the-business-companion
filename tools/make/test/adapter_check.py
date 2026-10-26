"""Run n8n_rule's adapter in Node with a simulated Make `input`, so an adapter change is
checked without spending Make credits.  python3 tools/make/test/adapter_check.py"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mk import n8n_build, n8n_rule  # noqa: E402


def run(code: str, inputs: dict, values: dict):
    """values: input key -> the value Make would pass (objects stay objects)."""
    src = ("const input = " + json.dumps({k: values.get(k) for k in inputs}) + ";\n"
           "console.log(JSON.stringify((function(){\n" + code + "\n})()));")
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(out.stderr)
    return json.loads(out.stdout)


def main() -> None:
    today = dt.date.today()
    r = n8n_build("R11.2")
    cfg = {"split_window_days": 14, "split_limits": [500, 10000], "no_po_limit": 500, "margin_working_days": 5,
           "price_drop_pct": 30, "price_approver": "tom@example.test"}
    req = {"id": "REQ-1", "version": 1, "amount": 2400, "created": today.isoformat(), "category": "store fixtures",
           "lines": [{"item": "shelf-unit", "unit_price": 240}], "comparison": {"checked": True},
           "quote": {"matches": True, "valid_until": (today + dt.timedelta(days=20)).isoformat(), "freight": "included"}}
    names = ["Config", "Read request", "Read supplier record", "Read policy list", "Read last prices paid", "Read recent requests"]
    code, inputs = n8n_rule(r.RULES_JS, {n: f"{{{{{i}.data}}}}" for i, n in enumerate(names)},
                            bodies={"status_body": "JSON.stringify({ status: out.status, total: out.total })"})
    data = [cfg, req, {"active": True, "hold": False}, {"allowed_categories": ["store fixtures"], "waiver_grantors": []},
            {"items": [{"item": "shelf-unit", "unit_price": 250}]}, {"items": []}]
    out = run(code, inputs, dict(zip(inputs, data)) | {"run_id": "x"})
    assert out["outcome"] == "pass" and json.loads(out["status_body"])["total"] == 2400, out
    print("R11.2 rules: pass", out["status_body"])

    code, inputs = n8n_rule(r.BACKSTOP_JS, {"Config": "{{1.result}}", "Read yesterday's POs": "{{2.data}}", "Read approved requests": "{{3.data}}"},
                            many=True, bodies={"po_text": "'PO ' + out.po"})
    out = run(code, inputs, dict(zip(inputs, [{"no_po_limit": 500}, {"items": [{"id": "PO-9", "amount": 1200}, {"id": "PO-1", "amount": 10}]}, {"items": []}])))
    assert [i["po_text"] for i in out["items"]] == ["PO PO-9"], out
    print("R11.2 backstop (many): pass", out)

    # per-item mode, item lists, isExecuted and $execution
    js = "return { json: { id: $json.id, n: $('Rows').all().length, morning: $('Morning').isExecuted, web: $('Web').isExecuted, run: $execution.id } };"
    code, inputs = n8n_rule(js, {"Rows": "{{5.array}}"}, items=("Rows",), executed=("Morning",), per_item=True)
    out = run(code, inputs, {"in0_Rows": [{"json": {"id": "a"}}, {"id": "b"}], "run_id": "R1"})
    assert out == {"items": [{"id": "a", "n": 2, "morning": True, "web": False, "run": "R1"}, {"id": "b", "n": 2, "morning": True, "web": False, "run": "R1"}]}, out
    print("per-item, lists, isExecuted, $execution: pass")


if __name__ == "__main__":
    main()
