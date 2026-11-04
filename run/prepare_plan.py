"""Resolve a frozen plan's archived prompt paths without modifying the original plan.

python3 run/prepare_plan.py run/plans-v1.1/main.jsonl local/main-plan.jsonl
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def prepare(source, destination):
    lines = []
    for raw in source.read_text().splitlines():
        request = json.loads(raw)
        for block in [request['system'], *request['blocks']]:
            original = block['path']
            relative = original[original.index('run/'):] if 'run/' in original else original
            path = (ROOT / relative).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                raise ValueError('Prompt path is outside the artifact or missing')
            if hashlib.sha256(path.read_bytes()).hexdigest() != block['sha256']:
                raise ValueError(f'Prompt checksum mismatch: {relative}')
            block['path'] = str(path)
        lines.append(json.dumps(request, sort_keys=True))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text('\n'.join(lines) + '\n')
    print(f'{len(lines)} requests; prompt checksums verified')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    prepare(Path(sys.argv[1]), Path(sys.argv[2]))
