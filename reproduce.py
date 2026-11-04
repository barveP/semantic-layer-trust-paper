"""Regenerate the publication outputs from the distributed trials and author annotations."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', action='store_true', help='also compile the PDF with Tectonic or latexmk')
    args = parser.parse_args()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', MPLCONFIGDIR=str(ROOT / 'local/matplotlib'))
    steps = [('audit-site/intake.py',), ('run/analyze.py', 'main'),
             ('paper/build_results.py', 'main'), ('paper/build_assets.py',), ('run/validate_artifact.py',)]
    for step in steps:
        subprocess.run([sys.executable, '-B', *step], cwd=ROOT, env=env, check=True)
    if args.pdf:
        subprocess.run(['sh', 'paper/build_pdf.sh'], cwd=ROOT, env=env, check=True)


if __name__ == '__main__':
    main()
