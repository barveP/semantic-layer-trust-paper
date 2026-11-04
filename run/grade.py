"""Execute and grade one stage of the wrong-layer study (sl1).

  grade.py <stage> [--fake-responses DIR]

1. Collect the trials of run/plans/<stage>.jsonl and each one's final dispatcher attempt
   (local/slstudy-runs/<stage>/<request_id>/a<n>/{result.json,response.txt}).
2. Parse each response as one JSON object (code fences tolerated).
3. Run every extracted SQL statement in the isolated executor container as the read-only
   user (harness/executor), together with the gold and faulty-gold queries.
4. Classify each trial (rules frozen with this file; see GRADING-RULES in the README):
   answer   correct (= gold_a) | fault_match (= faulty_gold) | other_wrong | exec_error |
            rejected (not a single SELECT) | no_answer (no response or unparsable JSON)
   D1       a concern with target "layer" whose object names something in the layer shown
   D2       a D1 concern whose object names the mutated element (or its changed column/synonym)
   silent   fault arms only: answer == fault_match and no D1 concern
5. Write results/<stage>-trials.jsonl (one row per trial) and results/<stage>-EXECUTION.json.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

import yaml

RUN = pathlib.Path(__file__).resolve().parent
STUDY = RUN.parent
REPO = STUDY
TASKS = STUDY / "tasks"
sys.path.insert(0, str(TASKS))
from results import same_result  # noqa: E402

LOCAL = REPO / "local"
IMAGE = "slstudy-executor:v1"
FAULT_ARMS = {"F1", "F2", "F1A", "F2A", "F1N", "F2N"}
TOKEN = re.compile(r"[a-z][a-z0-9_]*")


STAGES = {  # stage -> (questions file, layers dir, plan file)
    "pilot": ("questions-v1.yaml", "layers", "plans/pilot.jsonl"),
    "main": ("questions-v1.1.yaml", "layers-v1.1", "plans-v1.1/main.jsonl"),
}
# Grading amendment 01 (after the pilot, before the main run): a metric computed the way its
# description licenses counts as the same answer. TPC-DS injects NULLs into each column
# independently, so SUM(ss_ext_sales_price) and SUM(ss_quantity * ss_sales_price) differ on
# rows where one input is NULL (and likewise ss_net_profit vs ss_net_paid - ss_ext_wholesale_cost),
# although the values agree exactly wherever all inputs are present.
EQUIVALENT_FORMS = [("ss.ss_ext_sales_price", "(ss.ss_quantity * ss.ss_sales_price)"),
                    ("ss.ss_net_profit", "(ss.ss_net_paid - ss.ss_ext_wholesale_cost)")]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def variants(sql, grading):
    """The query itself, plus (grading v1.1) every combination of the licensed equivalent forms."""
    out = [sql]
    if grading == "v1.1":
        for old, new in EQUIVALENT_FORMS:
            if old in sql:
                out += [v.replace(old, new) for v in out]
    return out


# ---------------------------------------------------------------- executor

def execute(items, workdir):
    """Run [{trial_id, sql}] through the executor container; returns {trial_id: result}."""
    secrets = LOCAL / "slstudy-exec-secrets"
    secrets.mkdir(mode=0o700, exist_ok=True)
    acct = json.loads((LOCAL / "snowflake-slstudy" / "ACCOUNT.json").read_text())
    (secrets / "account.json").write_text(json.dumps({"account_identifier": acct["account_identifier"],
                                                      "ro_user": acct["ro_user"]}))
    (secrets / "ro_key.p8").write_bytes((REPO / acct["ro_private_key"]).read_bytes())
    for f in secrets.iterdir():
        f.chmod(0o600)
    inp, out = workdir / "in", workdir / "out"
    inp.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (inp / "sql.jsonl").write_text("".join(json.dumps(x) + "\n" for x in items))
    cmd = ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", "--read-only",
           "--tmpfs", "/tmp", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--memory", "1g", "--pids-limit", "128",
           "-v", f"{secrets}:/secrets:ro", "-v", f"{inp}:/in:ro", "-v", f"{out}:/out", IMAGE]
    subprocess.run(cmd, check=True, timeout=7200, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return {r["trial_id"]: r for r in map(json.loads, (out / "results.jsonl").read_text().splitlines())}


# ---------------------------------------------------------------- parsing and layer identifiers

def parse_response(text):
    if text is None:
        return None, "no response"
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None, "no JSON object"
    try:
        obj = json.loads(s[i:j + 1])
    except json.JSONDecodeError:
        return None, "invalid JSON"
    if not isinstance(obj, dict) or not isinstance(obj.get("sql"), str):
        return None, "no sql field"
    return obj, None


def tokens(text):
    return set(TOKEN.findall(str(text).lower()))


def layer_vocabulary(path):
    """Element names, columns used in expressions/relationships, and synonym phrases."""
    if path is None:
        return set(), set()
    m = yaml.safe_load(path.read_text())
    names, phrases = set(), set()

    def take(el):
        names.add(el["name"].lower())
        for d in el.get("expression", {}).get("dialects", []):
            names.update(t for t in tokens(d["expression"]) if "_" in t)
        ctx = el.get("ai_context")
        if isinstance(ctx, dict):
            phrases.update(s.lower() for s in ctx.get("synonyms", []))
    for d in m.get("datasets", []):
        names.add(d["name"].lower())
        for f in d.get("fields", []):
            take(f)
        for x in d.get("metrics", []) or []:
            take(x)
    for x in m.get("metrics", []) or []:
        take(x)
    for r in m.get("relationships", []) or []:
        names.add(r["name"].lower())
        names.update(c.lower() for c in r["from_columns"] + r["to_columns"])
        ctx = r.get("ai_context")
        if isinstance(ctx, dict):
            phrases.update(s.lower() for s in ctx.get("synonyms", []))
    return names, phrases


def locate_vocabulary(q, base_model):
    """What counts as naming the mutated element (D2): mutated ids, the identifiers a fault
    changed, the synonym moved, and for value-mapping faults the mapped column."""
    out = {x.lower() for x in q["mutated_ids"]}
    phrases = set()
    for e in q["fault"]:
        if e["kind"] == "synonym":
            phrases.add(e["synonym"].lower())
            continue
        if "expression" in e:
            base_expr = ""
            for d in base_model.get("datasets", []):
                for f in d.get("fields", []) + (d.get("metrics") or []):
                    if f["name"] == e["name"]:
                        base_expr = f["expression"]["dialects"][0]["expression"]
            for x in base_model.get("metrics", []):
                if x["name"] == e["name"]:
                    base_expr = x["expression"]["dialects"][0]["expression"]
            changed = {t for t in tokens(e["expression"]) ^ tokens(base_expr) if "_" in t}
            out |= changed
            if q["operator"] == "value_mapping":
                out |= {t for t in tokens(e["expression"]) if "_" in t}
        for k in ("from_columns", "to_columns"):
            out |= {c.lower() for c in e.get(k, [])}
    return out, phrases


def mentions(obj, names, phrases):
    if not obj:
        return False
    low = str(obj).lower()
    return bool(tokens(low) & names) or any(p in low for p in phrases)


# ---------------------------------------------------------------- main

def trial_files(stage, rid, fake):
    if fake:
        p = fake / f"{rid}.txt"
        return ({"status": "completed", "cost_micros": 0, "fake": True}, p.read_text() if p.exists() else None)
    base = LOCAL / "slstudy-runs" / stage / rid
    attempts = sorted(base.glob("a*"), key=lambda p: int(p.name[1:])) if base.exists() else []
    for a in reversed(attempts):
        if (a / "result.json").exists():
            result = json.loads((a / "result.json").read_text())
            text = (a / "response.txt").read_text() if (a / "response.txt").exists() else None
            return result, text
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--fake-responses", type=pathlib.Path)
    ap.add_argument("--out-name")
    ap.add_argument("--out-dir", type=pathlib.Path, default=STUDY / "results")
    ap.add_argument("--grading", choices=["v1", "v1.1"], default="v1.1",
                    help="v1 = exact gold only (as frozen for the pilot); v1.1 = with grading amendment 01")
    args = ap.parse_args()
    qfile, layers_dir, plan_file = STAGES[args.stage]
    LAYERS = TASKS / layers_dir
    questions = {q["id"]: q for q in yaml.safe_load((TASKS / qfile).read_text())["questions"]}
    base_model = yaml.safe_load((LAYERS / "C1.yaml").read_text())
    plan = [json.loads(x) for x in (RUN / plan_file).read_text().splitlines()]
    name = args.out_name or args.stage

    trials, items = [], []
    for line in plan:
        rid = line["request_id"]
        _, stage, qid, arm, model, rep = rid.split("-")
        result, text = trial_files(args.stage, rid, args.fake_responses)
        obj, perr = parse_response(text) if (result and result.get("status") == "completed") else (None, "not completed")
        t = {"trial_id": rid, "stage": stage, "qid": qid, "operator": questions[qid]["operator"], "arm": arm,
             "model": model, "rep": int(rep[1:]), "dispatch_status": (result or {}).get("status"),
             "cost_micros": (result or {}).get("cost_micros"), "usage": (result or {}).get("usage"),
             "parse_error": perr, "sql": obj.get("sql") if obj else None,
             "assumptions": obj.get("assumptions") if obj else None,
             "concerns": obj.get("concerns") if obj else None,
             "confidence": obj.get("confidence") if obj else None}
        trials.append(t)
        if obj:
            items.append({"trial_id": rid, "sql": obj["sql"]})
    for qid, q in questions.items():
        for k, sql in enumerate(variants(q["gold_a"], args.grading)):
            items.append({"trial_id": f"gold-{qid}-a{k}", "sql": sql})
        for k, sql in enumerate(variants(q["faulty_gold"], args.grading)):
            items.append({"trial_id": f"gold-{qid}-f{k}", "sql": sql})

    workdir = LOCAL / "slstudy-runs" / f"exec-{name}"
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    executed = execute(items, workdir)
    gold_errors = [k for k, v in executed.items() if k.startswith("gold-") and v["status"] != "ok"]
    if gold_errors:
        raise SystemExit(f"gold queries failed in the executor: {gold_errors}")
    gold_rows = {qid: [v["rows"] for k, v in executed.items() if k.startswith(f"gold-{qid}-a")] for qid in questions}
    faulty_rows = {qid: [v["rows"] for k, v in executed.items() if k.startswith(f"gold-{qid}-f")] for qid in questions}
    overlap = [qid for qid in questions if any(same_result(g, f) for g in gold_rows[qid] for f in faulty_rows[qid])]
    if overlap:
        raise SystemExit(f"a correct form equals a faulty form (not discriminable): {overlap}")

    vocab_cache = {}
    for t in trials:
        q = questions[t["qid"]]
        layer_key = {"C0": None, "C1": "C1", "C1A": "C1", "C1N": "C1", "C1a": "C1a", "C1b": "C1b"}.get(t["arm"], t["arm"][:2])
        path = None
        if layer_key in ("C1", "C1a", "C1b"):
            path = LAYERS / f"{layer_key}.yaml"
        elif layer_key:
            path = LAYERS / t["qid"] / f"{'E' if layer_key == 'E' else layer_key}.yaml"
        if path not in vocab_cache:
            vocab_cache[path] = layer_vocabulary(path)
        names, phrases = vocab_cache[path]
        loc_names, loc_phrases = locate_vocabulary(q, base_model)

        res = executed.get(t["trial_id"])
        if t["sql"] is None:
            answer = "no_answer"
        elif res["status"] == "rejected":
            answer = "rejected"
        elif res["status"] != "ok":
            answer = "exec_error"
        elif any(same_result(res["rows"], g) for g in gold_rows[t["qid"]]):
            answer = "correct"
        elif any(same_result(res["rows"], f) for f in faulty_rows[t["qid"]]):
            answer = "fault_match"
        else:
            answer = "other_wrong"
        concerns = t["concerns"] if isinstance(t["concerns"], list) else []
        layer_concerns = [c for c in concerns if isinstance(c, dict) and str(c.get("target", "")).lower() == "layer"
                          and mentions(c.get("object"), names, phrases)]
        d1 = bool(layer_concerns) if path is not None else None
        d2 = any(mentions(c.get("object"), loc_names, loc_phrases) for c in layer_concerns) if path is not None else None
        t.update(exec_status=res["status"] if res else None, exec_error=(res or {}).get("error"),
                 rows_returned=len(res["rows"]) if res and res.get("rows") is not None else None,
                 query_id=(res or {}).get("query_id"), answer=answer, d1=d1, d2=d2,
                 n_concerns=len(concerns),
                 silent=(answer == "fault_match" and not d1) if t["arm"] in FAULT_ARMS else None)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}-trials.jsonl").write_text("".join(json.dumps(t, default=str) + "\n" for t in trials))
    summary = {
        "kind": "fake-provider infrastructure test (not a result)" if args.fake_responses else f"graded stage {args.stage}",
        "started_utc": started, "trials": len(trials),
        "grader_sha256": sha(pathlib.Path(__file__).read_bytes()),
        "results_sha256": sha((TASKS / "results.py").read_bytes()),
        "questions_file": qfile, "questions_sha256": sha((TASKS / qfile).read_bytes()),
        "plan_file": plan_file, "plan_sha256": sha((RUN / plan_file).read_bytes()),
        "grading": args.grading,
        "gold_forms": {qid: [len(gold_rows[qid]), len(faulty_rows[qid])] for qid in questions},
        "executor_image": subprocess.run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
                                         capture_output=True, text=True).stdout.strip(),
        "executor_script_sha256": sha((STUDY / "harness" / "executor" / "execute.py").read_bytes()),
        "answer_counts": {},
    }
    for t in trials:
        summary["answer_counts"][t["answer"]] = summary["answer_counts"].get(t["answer"], 0) + 1
    (out_dir / f"{name}-EXECUTION.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["answer_counts"]))


if __name__ == "__main__":
    main()
