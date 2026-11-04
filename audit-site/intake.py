"""Compare the author's annotations with the deterministic detection rule.

Run from the repository root: python3 audit-site/intake.py
The ratings CSV contains item, trial_id, about_layer, identifies_fault and note.
Each sampled item must have one annotation. Bootstrap resampling keeps concerns
from the same trial together. The supplied judgments and notes remain in the CSV.
"""
import argparse
import csv
import hashlib
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / 'results/main-HUMAN-AUDIT-SAMPLE.csv'
RATINGS = ROOT / 'results/main-HUMAN-RATINGS.csv'
OUTPUT = ROOT / 'results/main-HUMAN-AUDIT-AGREEMENT.json'
TRIAL = re.compile(r'^(sl1-main-(Q\d\d)-([A-Za-z0-9]+)-(opus|sol|haiku)-r\d)#c\d+$')
FAULT_ARMS = {'F1', 'F2', 'F1A', 'F2A', 'F1N', 'F2N'}
TWO_FIELD_FAULTS = {'Q13', 'Q14', 'Q15', 'Q16'}
SEED, RESAMPLES = 20261031, 10000


def stats(pairs):
    n = len(pairs)
    if not n:
        return None
    a = sum(h and r for h, r in pairs)
    b = sum(not h and r for h, r in pairs)
    c = sum(h and not r for h, r in pairs)
    d = n - a - b - c
    po = (a + d) / n
    pe = ((a + b) * (a + c) + (c + d) * (b + d)) / n**2
    return {'n': n, 'both_yes': a, 'rule_only_yes': b, 'person_only_yes': c, 'both_no': d,
            'agreement': po, 'kappa': (po - pe) / (1 - pe) if pe != 1 else None,
            'rule_precision': a / (a + b) if a + b else None,
            'rule_recall': a / (a + c) if a + c else None,
            'person_yes_rate': (a + c) / n, 'rule_yes_rate': (a + b) / n}


def compare(rows, human, rule):
    clusters = {}
    for row in rows:
        clusters.setdefault(row['trial'], []).append((human(row), rule(row)))
    groups = list(clusters.values())
    result = stats([pair for group in groups for pair in group])
    if result is None:
        return None
    rng = random.Random(SEED)
    keys = ('agreement', 'kappa', 'rule_precision', 'rule_recall')
    draws = {key: [] for key in keys}
    for _ in range(RESAMPLES):
        sample = [pair for _ in groups for pair in groups[rng.randrange(len(groups))]]
        summary = stats(sample)
        for key in keys:
            if summary[key] is not None:
                draws[key].append(summary[key])
    result['ci95'] = {}
    for key, values in draws.items():
        values.sort()
        result['ci95'][key] = ([values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]]
                              if len(values) >= 100 else None)
    result['trials'] = len(groups)
    return result


def load_rows(sample_path=SAMPLE, ratings_path=RATINGS):
    with sample_path.open(newline='') as stream:
        sample = list(csv.DictReader(stream))
    with ratings_path.open(newline='') as stream:
        annotations = list(csv.DictReader(stream))
    expected = {row['item'] for row in sample}
    indexed = {row['item']: row for row in annotations}
    if len(indexed) != len(annotations) or set(indexed) != expected:
        raise ValueError('Ratings must contain each sampled item exactly once')
    rows = []
    for s in sample:
        rating = indexed[s['item']]
        match = TRIAL.fullmatch(s['trial_id'])
        if not match or rating['trial_id'] != s['trial_id']:
            raise ValueError(f"Trial identifier mismatch for item {s['item']}")
        arm = match.group(3)
        fault = arm in FAULT_ARMS
        if rating['about_layer'] not in ('yes', 'no'):
            raise ValueError(f"Invalid layer judgment for item {s['item']}")
        if rating['identifies_fault'] not in (('yes', 'no') if fault else ('na',)):
            raise ValueError(f"Invalid fault judgment for item {s['item']}")
        group = 'no layer' if arm == 'C0' else 'element removed' if arm == 'E' else 'planted mistake' if fault else 'correct layer'
        rows.append({'item': int(s['item']), 'trial': match.group(1), 'question': match.group(2),
                     'arm': arm, 'group': group, 'fault': fault,
                     'about': rating['about_layer'] == 'yes', 'identifies': rating['identifies_fault'] == 'yes',
                     'rule_d1': s['grader_d1_counted'] == 'True', 'rule_d2': s['grader_d2_counted'] == 'True',
                     'note': rating['note']})
    return rows


def report(rows, sample_path=SAMPLE, ratings_path=RATINGS):
    faulty = [row for row in rows if row['fault']]
    d1 = lambda rs: compare(rs, lambda r: r['about'], lambda r: r['rule_d1'])
    d2 = lambda rs: compare(rs, lambda r: r['about'] and r['identifies'], lambda r: r['rule_d2'])
    return {'kind': 'Human annotation agreement with the deterministic detection rule',
            'rater': 'Poorva Barve (one author)', 'complete': True, 'sample_size': len(rows),
            'complete_ratings': len(rows), 'notes_written': sum(bool(r['note'].strip()) for r in rows),
            'sample_csv_sha256': hashlib.sha256(sample_path.read_bytes()).hexdigest(),
            'ratings_csv_sha256': hashlib.sha256(ratings_path.read_bytes()).hexdigest(),
            'bootstrap': {'unit': 'trial', 'resamples': RESAMPLES, 'seed': SEED, 'interval': 'percentile 95%'},
            'D1_about_layer': d1(rows),
            'D1_by_arm_group': {g: d1([r for r in rows if r['group'] == g]) for g in
                                ('no layer', 'correct layer', 'element removed', 'planted mistake')},
            'D2_about_layer_and_identifies': d2(faulty),
            'D2_identifies_as_asked': compare(faulty, lambda r: r['identifies'], lambda r: r['rule_d2']),
            'D2_without_two_field_fiscal_faults': d2([r for r in faulty if r['question'] not in TWO_FIELD_FAULTS])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ratings', type=Path, default=RATINGS)
    parser.add_argument('--sample', type=Path, default=SAMPLE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = report(load_rows(args.sample, args.ratings), args.sample, args.ratings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'items': result['sample_size'], 'notes': result['notes_written'],
                      'D1_kappa': result['D1_about_layer']['kappa'],
                      'D2_kappa': result['D2_identifies_as_asked']['kappa']}))


if __name__ == '__main__':
    main()
