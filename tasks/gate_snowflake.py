"""Repeat the task gates on Snowflake, as the read-only study user, and compare engines.

For each question: gold_a, gold_b and faulty_gold run on SLSTUDY.TPCDS_SF1.
- discriminable: faulty_gold differs from gold_a (on Snowflake)
- gold_agree:    gold_b equals gold_a (on Snowflake)
- cross_engine:  Snowflake gold_a equals DuckDB gold_a (same data, two engines)
Writes gates/GATE-SNOWFLAKE-<date>.json. Preparation, not a study result.
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
sys.path.insert(0, str(TASKS.parent / "harness"))
from sf_connect import connect  # noqa: E402

REPO = TASKS.parent
DB = REPO / "local" / "slstudy-data" / "tpcds_sf1.duckdb"


def run(cur, sql):
    try:
        cur.execute(sql)
        return cur.fetchall(), getattr(cur, "sfqid", None), None
    except Exception as e:
        return None, None, f"{type(e).__name__}: {str(e)[:300]}"


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    qfile, bfile = f"questions-{version}.yaml", f"gold-b-{version}.yaml"
    spec = yaml.safe_load((TASKS / qfile).read_text())["questions"]
    gold_b = {g["id"]: g["sql"] for g in yaml.safe_load((TASKS / bfile).read_text())["queries"]}
    duck = duckdb.connect(str(DB), read_only=True)
    report, failures = [], []
    with connect("ro", schema="TPCDS_SF1") as con:
        cur = con.cursor()
        for q in spec:
            a, qa, ea = run(cur, q["gold_a"])
            f, qf, ef = run(cur, q["faulty_gold"])
            b, qb, eb = run(cur, gold_b[q["id"]])
            da = duck.execute(q["gold_a"]).fetchall()
            item = {
                "id": q["id"],
                "query_ids": {"gold_a": qa, "faulty_gold": qf, "gold_b": qb},
                "errors": {k: v for k, v in (("gold_a", ea), ("faulty_gold", ef), ("gold_b", eb)) if v},
                "gold_a_preview": None if a is None else [[str(v) for v in r] for r in a[:6]],
                "discriminable": a is not None and f is not None and not same_result(a, f),
                "gold_agree": a is not None and b is not None and same_result(a, b),
                "cross_engine": a is not None and same_result(a, da),
            }
            for k in ("discriminable", "gold_agree", "cross_engine"):
                if not item[k]:
                    failures.append(f"{q['id']}: {k} failed" + (f" {item['errors']}" if item["errors"] else ""))
            report.append(item)
    out = {
        "kind": "task-preparation gate on Snowflake as SLSTUDY_USER (not a study result)",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "question_set": version,
        "questions_sha256": hashlib.sha256((TASKS / qfile).read_bytes()).hexdigest(),
        "gold_b_sha256": hashlib.sha256((TASKS / bfile).read_bytes()).hexdigest(),
        "passed": not failures,
        "failures": failures,
        "questions": report,
    }
    gates = TASKS / "gates"
    path = gates / f"GATE-SNOWFLAKE-{datetime.date.today():%Y%m%d}{'' if version == 'v1' else '-' + version}.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"{'PASSED' if not failures else 'FAILED'}: {path}")
    for x in failures:
        print("  ", x)
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
