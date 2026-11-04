"""Fake-provider infrastructure test (gate 5 of protocol v0.2). Not a study result.

Writes one canned "model response" per pilot trial, cycling through ten behaviours with
known expected grades, runs grade.py on them (real executor container, real Snowflake,
read-only user) and checks every expected classification. Output: run/tests/.
"""
import json
import pathlib
import subprocess
import sys

import yaml

RUN = pathlib.Path(__file__).resolve().parent
STUDY = RUN.parent
REPO = STUDY
FAKE = REPO / "local" / "slstudy-runs" / "fake-responses"
OUT = RUN / "tests"
FAULT_ARMS = {"F1", "F2", "F1A", "F2A", "F1N", "F2N"}


def response(kind, q, arm):
    mutated = q["mutated_ids"][0]
    gold, faulty = q["gold_a"], q["faulty_gold"]
    body = {"assumptions": [], "concerns": [], "confidence": 0.8}
    if kind == 0:
        body["sql"] = gold
    elif kind == 1:
        body["sql"] = faulty
    elif kind == 2:
        body.update(sql=faulty, concerns=[{"target": "layer", "object": mutated, "text": "looks wrong"}])
    elif kind == 3:
        body.update(sql=gold, concerns=[{"target": "layer", "object": "store_sales", "text": "generic"}])
    elif kind == 4:
        body["sql"] = "DROP TABLE SLSTUDY.TPCDS_SF1.STORE"
    elif kind == 5:
        body["sql"] = "SELECT no_such_column FROM SLSTUDY.TPCDS_SF1.STORE_SALES"
    elif kind == 6:
        return "I think the answer is 42."
    elif kind == 7:
        body["sql"] = "SELECT 1"
        return "```json\n" + json.dumps(body) + "\n```"
    elif kind == 8:
        body["sql"] = "SELECT 1; SELECT 2"
    elif kind == 9:
        body.update(sql=gold, concerns=[{"target": "question", "object": mutated, "text": "ambiguous"}])
    return json.dumps(body)


def expected(kind, arm):
    has_layer = arm != "C0"
    exp = {0: "correct", 1: "fault_match", 2: "fault_match", 3: "correct", 4: "rejected", 5: "exec_error",
           6: "no_answer", 7: "other_wrong", 8: "rejected", 9: "correct"}[kind]
    d1 = {2: True, 3: True}.get(kind, False) if has_layer else None
    d2 = (kind == 2) if has_layer else None
    if kind in (6,):
        d1 = False if has_layer else None
        d2 = False if has_layer else None
    silent = (kind == 1) if arm in FAULT_ARMS else None
    return exp, d1, d2, silent


def main():
    grading = sys.argv[1] if len(sys.argv) > 1 else "v1"
    suffix = "" if grading == "v1" else f"-g{grading[1:]}"
    questions = {q["id"]: q for q in yaml.safe_load((STUDY / "tasks" / "questions-v1.yaml").read_text())["questions"]}
    plan = [json.loads(x) for x in (RUN / "plans" / "pilot.jsonl").read_text().splitlines()]
    FAKE.mkdir(parents=True, exist_ok=True)
    expect = {}
    for i, line in enumerate(plan):
        rid = line["request_id"]
        qid, arm = rid.split("-")[2], rid.split("-")[3]
        kind = i % 10
        (FAKE / f"{rid}.txt").write_text(response(kind, questions[qid], arm))
        expect[rid] = (kind,) + expected(kind, arm)
    subprocess.run([sys.executable, str(RUN / "grade.py"), "pilot", "--fake-responses", str(FAKE), "--grading", grading,
                    "--out-name", f"infra-test-fake{suffix}", "--out-dir", str(OUT)], check=True)
    rows = {json.loads(x)["trial_id"]: json.loads(x) for x in (OUT / f"infra-test-fake{suffix}-trials.jsonl").read_text().splitlines()}
    failures = []
    for rid, (kind, ans, d1, d2, silent) in expect.items():
        r = rows[rid]
        got = (r["answer"], r["d1"], r["d2"], r["silent"])
        if got != (ans, d1, d2, silent):
            failures.append({"trial": rid, "kind": kind, "expected": [ans, d1, d2, silent], "got": list(got)})
    report = {"kind": "fake-provider infrastructure test (not a study result)", "grading": grading, "trials": len(expect),
              "behaviours": 10, "passed": not failures, "failures": failures}
    (OUT / f"INFRA-TEST-RESULT{suffix}.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "failures": len(failures)}))
    for f in failures[:10]:
        print(f)
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
