"""Executor for agent-written SQL. Runs inside the isolated container only.

The container sees: this script, /secrets/ro_key.p8 and /secrets/account.json (read-only;
the read-only study user only), /in/sql.jsonl (read-only) and /out (write). It holds no
API keys and no host files. Each statement is parsed with sqlglot (Snowflake dialect) and
run only if it is exactly one SELECT or set operation (a WITH clause is allowed). It runs
as SLSTUDY_USER (SELECT-only role, 120 s statement cap set on the user). At most 10,000
rows are fetched.

Output: /out/results.jsonl, one object per input line:
  {trial_id, status: ok | rejected | error, rows, truncated, query_id, error, elapsed_s}
"""
import datetime
import decimal
import json
import time

import snowflake.connector
import sqlglot
from cryptography.hazmat.primitives import serialization
from sqlglot import exp

MAX_ROWS = 10_000


def check(sql):
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        return None, "empty statement"
    try:
        parsed = sqlglot.parse(sql, read="snowflake")
    except Exception as e:  # noqa: BLE001
        return None, f"parse error: {type(e).__name__}"
    parsed = [p for p in parsed if p is not None]
    if len(parsed) != 1:
        return None, f"{len(parsed)} statements"
    tree = parsed[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        return None, f"not a query: {type(tree).__name__}"
    for node in tree.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop,
                             exp.Alter, exp.Command, exp.Copy)):
            return None, f"forbidden node: {type(node).__name__}"
    return sql, None


def plain(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    return v


def main():
    acct = json.load(open("/secrets/account.json"))
    key = serialization.load_pem_private_key(open("/secrets/ro_key.p8", "rb").read(), password=None)
    der = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    con = snowflake.connector.connect(account=acct["account_identifier"], user=acct["ro_user"], private_key=der,
                                      role="SLSTUDY_RO", warehouse="SLSTUDY_WH", database="SLSTUDY",
                                      schema="TPCDS_SF1", session_parameters={"QUERY_TAG": "slstudy-executor"})
    cur = con.cursor()
    with open("/in/sql.jsonl") as src, open("/out/results.jsonl", "w") as out:
        for line in src:
            item = json.loads(line)
            result = {"trial_id": item["trial_id"], "rows": None, "truncated": False, "query_id": None, "error": None}
            sql, reason = check(item.get("sql") or "")
            started = time.monotonic()
            if sql is None:
                result.update(status="rejected", error=reason)
            else:
                try:
                    cur.execute(sql)
                    rows = cur.fetchmany(MAX_ROWS + 1)
                    result.update(status="ok", query_id=cur.sfqid, truncated=len(rows) > MAX_ROWS,
                                  rows=[[plain(v) for v in r] for r in rows[:MAX_ROWS]])
                except Exception as e:  # noqa: BLE001
                    result.update(status="error", query_id=getattr(cur, "sfqid", None),
                                  error=f"{type(e).__name__}: {str(e)[:300]}")
            result["elapsed_s"] = round(time.monotonic() - started, 3)
            out.write(json.dumps(result) + "\n")
            out.flush()
    con.close()


if __name__ == "__main__":
    main()
