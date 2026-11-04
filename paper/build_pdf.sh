#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p build
if command -v tectonic >/dev/null 2>&1; then
    tectonic --keep-logs --outdir build paper.tex
elif command -v latexmk >/dev/null 2>&1; then
    latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build paper.tex
else
    echo 'Install Tectonic or latexmk to compile the paper.' >&2
    exit 1
fi
cp build/paper.pdf paper.pdf
