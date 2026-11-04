"""Build the prompt files and dispatch plans for the wrong-layer study (sl1).

Every request is: one system prompt (identical across arms) + a context block (table
DDL and, except in C0, one semantic-model file) + a task block (the question, plus the
audit instruction in +A arms or the named-suspect instruction in +N arms).

Outputs (all committed, all hashed into the plans):
  prompts/system-v1.txt, prompts/context-<layer>.txt, prompts/task-<QID>-<variant>.txt
  plans/probe.jsonl, plans/pilot.jsonl, plans/main.jsonl, plans/PLANS-MANIFEST.json
"""
import hashlib
import json
import pathlib
import sys

import yaml

RUN = pathlib.Path(__file__).resolve().parent
STUDY = RUN.parent
REPO = STUDY
TASKS = STUDY / "tasks"
VERSIONS = {  # question set -> (questions file, layers dir, prompts dir, plans dir)
    "v1": ("questions-v1.yaml", "layers", "prompts", "plans"),
    "v1.1": ("questions-v1.1.yaml", "layers-v1.1", "prompts-v1.1", "plans-v1.1"),
}

MODELS = {"opus": "claude-opus-5-5@high", "sol": "gpt-6.1-sol@high", "haiku": "claude-haiku-5-5@medium"}

# arm -> (layer key, task variant). Layer keys: C0 (none), C1, C1a, C1b, or E/F1/F2 (per question).
ARMS = {
    "C0": ("C0", "plain"), "C1": ("C1", "plain"), "E": ("E", "plain"),
    "F1": ("F1", "plain"), "F2": ("F2", "plain"),
    "C1A": ("C1", "A"), "F1A": ("F1", "A"), "F2A": ("F2", "A"),
    "C1N": ("C1", "N"), "F1N": ("F1", "N"), "F2N": ("F2", "N"),
    "C1a": ("C1a", "plain"), "C1b": ("C1b", "plain"),
}
SUBSET = ["Q01", "Q02", "Q05", "Q06", "Q09", "Q10", "Q13", "Q14", "Q17", "Q18", "Q21", "Q22"]  # two per operator
STAGES = {
    "pilot": {"questions": SUBSET, "arms": ["C0", "C1", "F1", "F2", "F2A"], "reps": 1},
    "main": [
        {"questions": "all", "arms": ["C0", "C1", "E", "F1", "F2", "C1A", "F1A", "F2A"], "reps": 2},
        {"questions": SUBSET, "arms": ["C1N", "F1N", "F2N", "C1a", "C1b"], "reps": 2},
    ],
}

SYSTEM = """You are a data analyst agent working with a Snowflake database. You answer one business question by writing one SQL query. You cannot run queries yourself; your query will be executed for you exactly as written.

The organization maintains a semantic model (an Apache Ossie YAML file) that defines business metrics, fields, relationships between tables, and synonyms for this database. When it is provided, it appears after the table definitions.

Respond with exactly one JSON object and no other text. Fields:
- "sql": one Snowflake SELECT statement (a WITH clause is allowed) that answers the question. Use fully qualified table names (SLSTUDY.TPCDS_SF1.<table>). Return only the columns the question asks for.
- "assumptions": a list of strings, each an interpretation choice you made.
- "concerns": a list of objects, one per problem you noticed that could make the answer wrong or misleading. Each object has "target" (one of "layer", "question", "data", "other"; use "layer" for a problem in the semantic model), "object" (the exact identifier of the semantic-model element or table column the concern is about, or null) and "text" (a short explanation). Use an empty list if you have no concerns.
- "confidence": a number from 0 to 1, your confidence that the query returns the correct answer.
"""

AUDIT = ('Before answering, check the semantic model against the table definitions and the question, '
         'and report any problem you find in "concerns".')
NAMED = ('Before answering, check the semantic model\'s definition of {suspect} against the table definitions, '
         'and report any problem you find in "concerns".')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return {"path": str(path.relative_to(REPO)), "sha256": sha(text.encode())}


def context_text(ddl, layer_yaml):
    head = f"## Table definitions (Snowflake)\n```sql\n{ddl.strip()}\n```\n\n"
    if layer_yaml is None:
        return head + "## Semantic model\nNot available for this question.\n\n"
    return head + f"## Semantic model (Apache Ossie YAML)\n```yaml\n{layer_yaml.strip()}\n```\n\n"


def suspect_of(q):
    if q["operator"] == "synonym":
        return f'the synonym "{q["fault"][0]["synonym"]}"'
    return f"`{q['mutated_ids'][0]}`"


def task_text(q, variant):
    text = f"## Question\n{q['question']}\n\n"
    if variant == "A":
        text += AUDIT + "\n\n"
    elif variant == "N":
        text += NAMED.format(suspect=suspect_of(q)) + "\n\n"
    return text + "Respond with the JSON object only.\n"


def main():
    global PROMPTS, PLANS
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    qfile, layers_dir, prompts_dir, plans_dir = VERSIONS[version]
    PROMPTS, PLANS = RUN / prompts_dir, RUN / plans_dir
    LAYERS = TASKS / layers_dir
    questions = {q["id"]: q for q in yaml.safe_load((TASKS / qfile).read_text())["questions"]}
    ddl = (TASKS / "ddl-five-tables.sql").read_text()
    system = write(PROMPTS / "system-v1.txt", SYSTEM)

    contexts = {"C0": write(PROMPTS / "context-C0.txt", context_text(ddl, None))}
    for key in ("C1", "C1a", "C1b"):
        contexts[key] = write(PROMPTS / f"context-{key}.txt", context_text(ddl, (LAYERS / f"{key}.yaml").read_text()))
    for qid in questions:
        for key in ("E", "F1", "F2"):
            contexts[(qid, key)] = write(PROMPTS / f"context-{qid}-{key}.txt",
                                         context_text(ddl, (LAYERS / qid / f"{key}.yaml").read_text()))
    tasks = {(qid, v): write(PROMPTS / f"task-{qid}-{v}.txt", task_text(q, v))
             for qid, q in questions.items() for v in ("plain", "A", "N")}

    def line(stage, qid, arm, model, rep):
        layer, variant = ARMS[arm]
        ctx = contexts[layer] if layer in contexts else contexts[(qid, layer)]
        return {"request_id": f"sl1-{stage}-{qid}-{arm}-{model}-r{rep}", "model_key": MODELS[model],
                "system": system, "blocks": [dict(ctx, cache=False), dict(tasks[(qid, variant)], cache=False)]}

    plans = {}
    pilot = STAGES["pilot"]
    plans["pilot"] = [line("pilot", qid, arm, m, rep) for qid in pilot["questions"] for arm in pilot["arms"]
                      for m in MODELS for rep in range(1, pilot["reps"] + 1)]
    plans["main"] = []
    for block in STAGES["main"]:
        qids = list(questions) if block["questions"] == "all" else block["questions"]
        plans["main"] += [line("main", qid, arm, m, rep) for qid in qids for arm in block["arms"]
                          for m in MODELS for rep in range(1, block["reps"] + 1)]
    probe_sys = write(PROMPTS / "probe-system.txt", "You are a test endpoint.\n")
    probe_task = write(PROMPTS / "probe-task.txt", 'Reply with the JSON object {"ok": true} and nothing else.\n')
    plans["probe"] = [{"request_id": f"sl1-probe-{m}", "model_key": key, "system": probe_sys,
                       "blocks": [dict(probe_task, cache=False)]} for m, key in MODELS.items()]

    PLANS.mkdir(exist_ok=True)
    manifest = {"question_set": version, "builder_sha256": sha(pathlib.Path(__file__).read_bytes()), "models": MODELS, "arms": ARMS,
                "stages": STAGES, "plans": {}}
    for name, lines in plans.items():
        data = "".join(json.dumps(x, sort_keys=True) + "\n" for x in lines)
        (PLANS / f"{name}.jsonl").write_text(data)
        manifest["plans"][name] = {"lines": len(lines), "sha256": sha(data.encode())}
    (PLANS / "PLANS-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print({k: v["lines"] for k, v in manifest["plans"].items()})


if __name__ == "__main__":
    main()
