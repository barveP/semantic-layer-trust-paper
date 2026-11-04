"""Discriminability and gold-agreement gates on the local DuckDB copy of TPC-DS SF1.

For each question: run gold_a and faulty_gold (and gold_b when gold-b-v1.yaml exists).
- discriminable: faulty_gold's result differs from gold_a's.
- gold_agree:    gold_b's result equals gold_a's.
Writes gates/GATE-LOCAL-<date>.json. The same data are loaded into Snowflake, where
the gate is repeated once access works; this local run is preparation, not a result.
"""
import datetime
import hashlib
import json
import pathlib
import sys

import duckdb
import yaml

from results import same_result

TASKS = pathlib.Path(__file__).resolve().parent
REPO = TASKS.parent
DB = REPO / "local" / "slstudy-data" / "tpcds_sf1.duckdb"


def run(con, sql):
    try:
        return con.execute(sql).fetchall(), None
    except Exception as e:  # report, never hide
        return None, f"{type(e).__name__}: {str(e)[:300]}"


def preview(rows):
    return None if rows is None else [[str(v) for v in r] for r in rows[:12]]


def main():
    spec = yaml.safe_load((TASKS / "questions-v1.yaml").read_text())["questions"]
    gold_b_path = TASKS / "gold-b-v1.yaml"
    gold_b = {}
    if gold_b_path.exists():
        gold_b = {g["id"]: g["sql"] for g in yaml.safe_load(gold_b_path.read_text())["queries"]}
    con = duckdb.connect(str(DB), read_only=True)

    report, failures = [], []
    for q in spec:
        ordered = False
        a, ea = run(con, q["gold_a"])
        f, ef = run(con, q["faulty_gold"])
        item = {"id": q["id"], "operator": q["operator"],
                "gold_a_error": ea, "faulty_error": ef,
                "gold_a_rows": None if a is None else len(a),
                "gold_a_preview": preview(a), "faulty_preview": preview(f)}
        item["discriminable"] = (a is not None and f is not None and not same_result(a, f, ordered))
        if not item["discriminable"]:
            failures.append(f"{q['id']}: not discriminable" + (f" ({ea or ef})" if ea or ef else ""))
        if a is not None and len(a) == 0:
            failures.append(f"{q['id']}: gold_a returns no rows")
        if q["id"] in gold_b:
            b, eb = run(con, gold_b[q["id"]])
            item["gold_b_error"] = eb
            item["gold_b_preview"] = preview(b)
            item["gold_agree"] = (a is not None and b is not None and same_result(a, b, ordered))
            if not item["gold_agree"]:
                failures.append(f"{q['id']}: gold_a and gold_b disagree" + (f" ({eb})" if eb else ""))
        report.append(item)

    out = {
        "kind": "task-preparation gate on local DuckDB (not a study result)",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "duckdb": duckdb.__version__,
        "questions_sha256": hashlib.sha256((TASKS / "questions-v1.yaml").read_bytes()).hexdigest(),
        "gold_b_sha256": hashlib.sha256(gold_b_path.read_bytes()).hexdigest() if gold_b else None,
        "passed": not failures,
        "failures": failures,
        "questions": report,
    }
    gates = TASKS / "gates"
    gates.mkdir(exist_ok=True)
    name = f"GATE-LOCAL-{datetime.date.today():%Y%m%d}{'-with-gold-b' if gold_b else ''}.json"
    (gates / name).write_text(json.dumps(out, indent=2) + "\n")
    print(f"{'PASSED' if not failures else 'FAILED'}: {gates / name}")
    for x in failures:
        print("  ", x)
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
