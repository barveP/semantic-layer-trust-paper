"""Build the Layer Audit page: the human audit of the detection rule, for local browser annotation.

  python3 build_site.py [--version v1]

Reads results/main-HUMAN-AUDIT-SAMPLE.csv (417 concerns, drawn by run/audit_sample.py), the questions file and the
correct layer, and writes to the ignored local/slstudy-audit-site/<version>/:
  index.html     the page in the form the artifact host expects (no document skeleton), with style.css, app.js and the
                 items inlined
  MANIFEST.json  hashes of the page, its sources, the sample CSV and the item list

The page is blind by construction: it carries no grader labels, trial ids, model names or arm names, only what the
rater needs (the question, what was planted and how, the agent's concern). The build stops if any of those leak.
"""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parent
SAMPLE = STUDY / 'results' / 'main-HUMAN-AUDIT-SAMPLE.csv'
QUESTIONS = STUDY / 'tasks' / 'questions-v1.1.yaml'
LAYER = STUDY / 'tasks' / 'layers-v1.1' / 'C1.yaml'
TRIAL = re.compile(r'^sl1-main-(Q\d\d)-([A-Za-z0-9]+)-(opus|sol|haiku)-r\d#c\d+$')
FAULT_ARMS = {'F1', 'F2', 'F1A', 'F2A', 'F1N', 'F2N'}
CORRECT_ARMS = {'C1', 'C1A', 'C1N', 'C1a', 'C1b'}
LEAKS = [r'grader', r'sl1-', r'\bopus\b', r'\bhaiku\b', r'\bsol\b', r'\bgpt', r'\bF1A\b', r'\bF2N\b', r'\bC1N\b', r'd1_counted', r'd2_counted']


def sha(b):
    return hashlib.sha256(b).hexdigest()


def expr(node):
    return node['expression']['dialects'][0]['expression']


def correct_version(e, model):
    """The faulted element as the correct layer has it, in the same form as planted_version()."""
    if e['kind'] == 'metric':
        m = next(m for m in model['metrics'] if m['name'] == e['name'])
        return f"{e['name']} = {expr(m)}"
    if e['kind'] == 'dataset_metric':
        ds = next(d for d in model['datasets'] if d['name'] == e['dataset'])
        m = next(m for m in ds['metrics'] if m['name'] == e['name'])
        return f"{e['dataset']}.{e['name']} = {expr(m)}"
    if e['kind'] == 'field':
        ds = next(d for d in model['datasets'] if d['name'] == e['dataset'])
        f = next(f for f in ds['fields'] if f['name'] == e['name'])
        return f"{e['dataset']}.{e['name']} = {expr(f)}"
    if e['kind'] == 'relationship':
        r = next(r for r in model['relationships'] if r['name'] == e['name'])
        return join(r, r['from_columns'], r['to_columns'])
    if e['kind'] == 'synonym':
        return f"\"{e['synonym']}\" is a synonym of {e['from']['name']}"
    raise ValueError(e['kind'])


def planted_version(e, model):
    if e['kind'] in ('metric',):
        return f"{e['name']} = {e['expression']}"
    if e['kind'] in ('dataset_metric', 'field'):
        return f"{e['dataset']}.{e['name']} = {e['expression']}"
    if e['kind'] == 'relationship':
        r = next(r for r in model['relationships'] if r['name'] == e['name'])
        return join(r, e.get('from_columns') or r['from_columns'], e.get('to_columns') or r['to_columns'])
    if e['kind'] == 'synonym':
        return f"\"{e['synonym']}\" is a synonym of {e['to']['name']} (moved from {e['from']['name']})"
    raise ValueError(e['kind'])


def join(r, fc, tc):
    return ' AND '.join(f"{r['from']}.{a} = {r['to']}.{b}" for a, b in zip(fc, tc)) + f"  (relationship {r['name']})"


KIND_WORDS = {'metric': 'metric', 'dataset_metric': 'metric', 'field': 'field', 'relationship': 'relationship', 'synonym': 'synonym'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', default='v1')
    args = parser.parse_args()
    model = yaml.safe_load(LAYER.read_text())
    questions = {q['id']: q for q in yaml.safe_load(QUESTIONS.read_text())['questions']}
    rows = list(csv.DictReader(SAMPLE.open(newline='')))
    items = []
    for r in rows:
        m = TRIAL.match(r['trial_id'])
        assert m, r['trial_id']
        qid, arm = m.group(1), m.group(2)
        q = questions[qid]
        assert q['question'] == r['question'], qid
        it = {'n': int(r['item']), 'question': q['question'], 'target': r['concern_target'], 'object': r['concern_object'],
              'text': r['concern_text']}
        if arm == 'C0':
            it['kind'] = 'nolayer'
        elif arm in CORRECT_ARMS:
            it['kind'] = 'none'
        elif arm == 'E':
            it['kind'] = 'removed'
            it['element'] = q['mutated_ids'][0]
        else:
            assert arm in FAULT_ARMS, arm
            e = q['fault'][0]
            it.update(kind='fault', element=e.get('name') or e.get('synonym'), element_kind=KIND_WORDS[e['kind']],
                      planted='; '.join(planted_version(edit, model) for edit in q['fault']),
                      correct='; '.join(correct_version(edit, model) for edit in q['fault']),
                      description_matches=arm.startswith('F1'))
        items.append(it)
    assert [it['n'] for it in items] == list(range(1, len(items) + 1)), 'items must be numbered 1..N in order'
    items_json = json.dumps(items, ensure_ascii=False, separators=(',', ':'))
    data = {'version': args.version, 'items_sha256': sha(items_json.encode()), 'count': len(items), 'items': items,
            'layer_yaml': LAYER.read_text(), 'sample_csv_sha256': sha(SAMPLE.read_bytes())}
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    page = (HERE / 'page.html').read_text()
    css, app = (HERE / 'style.css').read_text(), (HERE / 'app.js').read_text()
    assert '</script' not in app.lower() and '</style' not in css.lower(), 'inlined code must not close its own tag'
    page = page.replace('/*STYLE*/', css).replace('/*APP*/', app).replace('/*DATA*/', blob)
    for pat in LEAKS:
        hit = re.search(pat, page, re.I)
        assert not hit, f'blindness: {pat!r} found in the page near {page[max(0, hit.start() - 60):hit.end() + 60]!r}'
    out = ROOT / 'local' / 'slstudy-audit-site' / args.version
    out.mkdir(parents=True, exist_ok=True)
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Layer Audit</title></head><body>' + page + '</body></html>')
    (out / 'index.html').write_text(page)
    manifest = {'schema': 'layer-audit-site-build-v1', 'version': args.version, 'page_sha256': sha(page.encode()),
                'page_bytes': len(page.encode()), 'items': len(items), 'items_sha256': data['items_sha256'],
                'sample_csv_sha256': sha(SAMPLE.read_bytes()), 'questions_sha256': sha(QUESTIONS.read_bytes()),
                'layer_sha256': sha(LAYER.read_bytes()),
                'sources_sha256': {n: sha((HERE / n).read_bytes()) for n in ('page.html', 'style.css', 'app.js', 'build_site.py')},
                'kinds': {k: sum(1 for it in items if it['kind'] == k) for k in ('fault', 'removed', 'none', 'nolayer')}}
    (out / 'MANIFEST.json').write_text(json.dumps(manifest, indent=1) + '\n')
    print(json.dumps({'out': str(out / 'index.html'), **{k: manifest[k] for k in ('page_bytes', 'items', 'kinds', 'page_sha256')}}, indent=1))


if __name__ == '__main__':
    main()
