"""Validate publication inputs, annotation joins and reported aggregates without external services."""
import csv
import hashlib
import importlib.util
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(name):
    return json.loads((ROOT / name).read_text())


def main():
    trials = [json.loads(line) for line in (ROOT / 'results/main-trials.jsonl').read_text().splitlines()]
    analysis = read('results/main-ANALYSIS.json')
    execution = read('results/main-EXECUTION.json')
    assert len(trials) == len({t['trial_id'] for t in trials}) == execution['trials'] == 1512
    assert dict(Counter(t['answer'] for t in trials)) == execution['answer_counts'] == analysis['answer_counts']
    assert all(t['dispatch_status'] == 'completed' for t in trials)
    assert {t['model'] for t in trials} == {'opus', 'sol', 'haiku'}
    for row in analysis['by_model_arm']:
        group = [t for t in trials if (t['model'], t['arm']) == (row['model'], row['arm'])]
        assert len(group) == row['n']
        for outcome in ('correct', 'fault_match', 'other_wrong'):
            assert math.isclose(sum(t['answer'] == outcome for t in group) / len(group), row[outcome])
    assert 'p_value' not in analysis['hypotheses']['X4']['gee_check']
    for row in analysis['flagged_following'].values():
        assert 0 <= row['located_concern'] <= row['any_layer_concern'] <= row['followed']
    assert sum(analysis['flagged_following'][f'{m}/F1']['located_concern'] for m in ('opus', 'sol', 'haiku')) == 33
    spec = importlib.util.spec_from_file_location('annotation_intake', ROOT / 'audit-site/intake.py')
    intake = importlib.util.module_from_spec(spec); spec.loader.exec_module(intake)
    annotations = intake.load_rows()
    assert len(annotations) == 417 and all(row['note'].strip() for row in annotations)
    report = read('results/main-HUMAN-AUDIT-AGREEMENT.json')
    assert report['ratings_csv_sha256'] == hashlib.sha256(intake.RATINGS.read_bytes()).hexdigest()
    assert report['sample_csv_sha256'] == hashlib.sha256(intake.SAMPLE.read_bytes()).hexdigest()
    for key, subset, label in [('D1_about_layer', annotations, 'about'),
                               ('D2_identifies_as_asked', [r for r in annotations if r['fault']], 'identifies')]:
        rule = 'rule_d1' if label == 'about' else 'rule_d2'
        stats = intake.stats([(r[label], r[rule]) for r in subset])
        for name, value in stats.items():
            assert report[key][name] == value
    freeze = read('operations/FREEZE-MAIN.json')
    plan = ROOT / 'run/plans-v1.1/main.jsonl'
    assert hashlib.sha256(plan.read_bytes()).hexdigest() == freeze['files_sha256']['run/plans-v1.1/main.jsonl']
    prompts = {}
    for line in plan.read_text().splitlines():
        request = json.loads(line)
        for block in [request['system'], *request['blocks']]:
            relative = block['path'][block['path'].index('run/'):]
            prompts[relative] = block['sha256']
    for name, expected in prompts.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    print(json.dumps({'trials': len(trials), 'annotations': len(annotations), 'notes': report['notes_written'],
                      'verified_prompt_files': len(prompts), 'D1_kappa': report['D1_about_layer']['kappa'],
                      'D2_kappa': report['D2_identifies_as_asked']['kappa'], 'checks': 'passed'}))


if __name__ == '__main__':
    main()
