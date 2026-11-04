"""Gate 5: both service users connect, and the executor role cannot write.

Writes a receipt (no secrets, no account identifier) to operations/receipts/.
Exit status 0 only if every check passes.
"""
import datetime
import json
import pathlib
import sys

from snowflake.connector.errors import ProgrammingError

from sf_connect import connect

STUDY = pathlib.Path(__file__).resolve().parents[1]


def session_facts(cur):
    cur.execute(
        "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), "
        "CURRENT_REGION(), CURRENT_VERSION()"
    )
    user, role, wh, region, version = cur.fetchone()
    cur.execute("SHOW PARAMETERS LIKE 'STATEMENT_TIMEOUT_IN_SECONDS' IN SESSION")
    timeout = cur.fetchone()[1]
    return {"user": user, "role": role, "warehouse": wh, "region": region,
            "snowflake_version": version, "session_statement_timeout_s": timeout}


def main():
    checks = {}
    with connect("loader") as con:
        cur = con.cursor()
        checks["loader"] = session_facts(cur)
        cur.execute("CREATE SCHEMA IF NOT EXISTS SLSTUDY.CONNECTION_PROBE")
        cur.execute("DROP SCHEMA SLSTUDY.CONNECTION_PROBE")
        checks["loader"]["can_create_schema"] = True

    with connect("ro") as con:
        cur = con.cursor()
        checks["ro"] = session_facts(cur)
        try:
            cur.execute("CREATE SCHEMA SLSTUDY.RO_WRITE_PROBE")
            cur.execute("DROP SCHEMA SLSTUDY.RO_WRITE_PROBE")
            checks["ro"]["write_refused"] = False
        except ProgrammingError as e:
            checks["ro"]["write_refused"] = True
            checks["ro"]["write_refusal_errno"] = e.errno

    ok = (
        checks["loader"]["role"] == "SLSTUDY_LOADER"
        and checks["ro"]["role"] == "SLSTUDY_RO"
        and checks["ro"]["write_refused"]
        and checks["ro"]["session_statement_timeout_s"] == "120"
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    receipt = {
        "kind": "infrastructure check (gate 5), not a study result",
        "utc": now.isoformat(timespec="seconds"),
        "account": "owner's Snowflake trial account; identifier in local/snowflake-slstudy/ACCOUNT.json",
        "checks": checks,
        "passed": ok,
    }
    out = STUDY / "operations" / "receipts" / f"connection-check-{now:%Y%m%dT%H%M%SZ}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    print(f"receipt: {out}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
