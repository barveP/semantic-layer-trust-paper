#!/usr/bin/env python3
"""Dispatcher for the wrong-layer study: an external audited LLM dispatcher, unchanged,
with this study's request-ID prefix (sl1-).

The dispatcher itself is not part of this repository. Point SL_DISPATCHER_DIR at the
directory that holds its dispatch.py and models.py; their hashes at run time are in
operations/FREEZE-*.json as "(msr) operations/llm/...". It keeps a cumulative cost
ledger, reserves each attempt at the adapter ceiling, never resends an attempt, records
pending liabilities on ambiguous failures, enforces a run envelope and writes outputs
under the ignored local/. Usage:

  SL_DISPATCHER_DIR=/path/to/llm dispatch_sl.py --plan run/plans/pilot.jsonl \
      --out-root local/slstudy-runs/pilot --envelope-usd 20 --execute
"""
import os
import re
import sys
from pathlib import Path

DISPATCHER = os.environ.get("SL_DISPATCHER_DIR")
if not DISPATCHER or not (Path(DISPATCHER) / "dispatch.py").is_file():
    sys.exit("set SL_DISPATCHER_DIR to the directory holding the dispatcher's dispatch.py")
sys.path.insert(0, DISPATCHER)
import dispatch  # noqa: E402

dispatch.ID_PATTERN = re.compile(r"sl1-[A-Za-z0-9_.:-]{3,120}")

if __name__ == "__main__":
    sys.exit(dispatch.main())
