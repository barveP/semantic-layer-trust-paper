"""Draw the human-audit sample of concerns (protocol v0.2 section 5) from a graded stage.

  audit_sample.py <stage>  ->  results/<stage>-HUMAN-AUDIT-SAMPLE.csv

A 20% random sample (seed 20261031) of all concerns, stratified by arm. For each concern
the rater sees the question, the layer element that was faulted (if any) and how, and the
concern; then marks two columns: is it about the semantic layer (D1 valid?) and does it
identify the planted fault (D2 valid?). The grader's labels are in separate columns so the
rater can be shown them or not. Ratings are kept separate from model output.
"""
import csv
import json
import pathlib
import random
import sys

import yaml

RUN = pathlib.Path(__file__).resolve().parent
STUDY = RUN.parent
sys.path.insert(0, str(RUN))
import grade  # noqa: E402  (its matching functions only; classification is not re-run)
QFILES = {"main": ("questions-v1.1.yaml", "layers-v1.1"), "pilot": ("questions-v1.yaml", "layers"),
          "pilot-g1.1": ("questions-v1.yaml", "layers")}


def layer_path(layers, t):
    key = {"C0": None, "C1": "C1", "C1A": "C1", "C1N": "C1", "C1a": "C1a", "C1b": "C1b"}.get(t["arm"], t["arm"][:2])
    if key is None:
        return None
    return layers / f"{key}.yaml" if key in ("C1", "C1a", "C1b") else layers / t["qid"] / f"{key}.yaml"


def describe_fault(q, arm):
    if arm == "C0":
        return "no semantic layer shown"
    if arm[:2] not in ("F1", "F2"):
        return "none (correct layer)" if arm != "E" else f"none; element removed: {q['mutated_ids'][0]}"
    e = q["fault"][0]
    if e["kind"] == "synonym":
        return f"synonym '{e['synonym']}' moved from {e['from']['name']} to {e['to']['name']}"
    if "expression" in e:
        return f"{e['name']} expression changed to: {e['expression']}"
    return f"{e['name']} columns changed to: {e.get('from_columns') or e.get('to_columns')}"


def main():
    stage = sys.argv[1]
    qfile, layers_dir = QFILES[stage]
    layers = STUDY / "tasks" / layers_dir
    questions = {q["id"]: q for q in yaml.safe_load((STUDY / "tasks" / qfile).read_text())["questions"]}
    base_model = yaml.safe_load((layers / "C1.yaml").read_text())
    trials = [json.loads(x) for x in (STUDY / "results" / f"{stage}-trials.jsonl").read_text().splitlines()]
    rows = []
    for t in trials:
        for i, c in enumerate(t.get("concerns") or []):
            if isinstance(c, dict):
                rows.append((t, i, c))
    rng = random.Random(20261031)
    by_arm = {}
    for r in rows:
        by_arm.setdefault(r[0]["arm"], []).append(r)
    sample = []
    for arm in sorted(by_arm):
        items = by_arm[arm]
        k = max(1, round(0.2 * len(items)))
        sample += rng.sample(items, k)
    rng.shuffle(sample)
    out = STUDY / "results" / f"{stage}-HUMAN-AUDIT-SAMPLE.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "trial_id", "question", "planted_fault", "concern_target", "concern_object", "concern_text",
                    "RATER_about_semantic_layer(yes/no)", "RATER_identifies_planted_fault(yes/no/na)", "RATER_note",
                    "grader_d1_counted", "grader_d2_counted"])
        for n, (t, i, c) in enumerate(sample, 1):
            q = questions[t["qid"]]
            path = layer_path(layers, t)
            names, phrases = grade.layer_vocabulary(path)
            loc_names, loc_phrases = grade.locate_vocabulary(q, base_model)
            is_d1 = path is not None and str(c.get("target", "")).lower() == "layer" and grade.mentions(c.get("object"), names, phrases)
            is_d2 = is_d1 and grade.mentions(c.get("object"), loc_names, loc_phrases)
            w.writerow([n, f"{t['trial_id']}#c{i}", q["question"], describe_fault(q, t["arm"]), c.get("target"),
                        c.get("object"), c.get("text"), "", "", "", is_d1, is_d2])
    print(f"{len(sample)} of {len(rows)} concerns -> {out}")


if __name__ == "__main__":
    main()
