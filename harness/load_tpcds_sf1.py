"""Generate TPC-DS SF1 with DuckDB's dsdgen, load it into SLSTUDY.TPCDS_SF1, verify.

Verification compares, per table, the row count and one aggregate per column
computed independently in DuckDB and in Snowflake: SUM for numbers, SUM(LENGTH)
for strings, SUM of days since 1970-01-01 for dates, plus the null count. Any
mismatch fails the load.

  --local-only   generate, export Parquet, write DDL and DuckDB checksums; no Snowflake
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import sys
from decimal import Decimal

import duckdb

STUDY = pathlib.Path(__file__).resolve().parents[1]
REPO = STUDY
WORK = REPO / "local" / "slstudy-data"
DB_FILE = WORK / "tpcds_sf1.duckdb"
PARQUET = WORK / "tpcds_sf1"
SCHEMA = "TPCDS_SF1"


def sf_type(duck_type):
    if duck_type == "INTEGER":
        return "INTEGER"
    if duck_type == "VARCHAR":
        return "VARCHAR"
    if duck_type == "DATE":
        return "DATE"
    m = re.fullmatch(r"DECIMAL\((\d+),(\d+)\)", duck_type)
    if m:
        return f"NUMBER({m[1]},{m[2]})"
    raise ValueError(f"unmapped DuckDB type {duck_type}")


def column_aggregate(col, duck_type, dialect):
    if duck_type == "VARCHAR":
        return f"SUM(LENGTH({col}))"
    if duck_type == "DATE":
        if dialect == "duckdb":
            return f"SUM({col} - DATE '1970-01-01')"
        return f"SUM(DATEDIFF(day, DATE '1970-01-01', {col}))"
    return f"SUM({col})"


def checksums(run_query, columns_by_table, dialect):
    out = {}
    for table, cols in columns_by_table.items():
        parts = ["COUNT(*)"]
        for col, t in cols:
            parts.append(column_aggregate(col, t, dialect))
            parts.append(f"COUNT(*) - COUNT({col})")
        row = run_query(f"SELECT {', '.join(parts)} FROM {table}")
        vals = [str(v) if v is not None else None for v in row]
        out[table] = {"rows": int(vals[0]), "columns": {}}
        for i, (col, _) in enumerate(cols):
            out[table]["columns"][col] = {"agg": vals[1 + 2 * i], "nulls": int(vals[2 + 2 * i])}
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_and_export():
    WORK.mkdir(parents=True, exist_ok=True)
    PARQUET.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_FILE))
    con.execute("INSTALL tpcds; LOAD tpcds;")
    if not con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'store_sales'").fetchone()[0]:
        con.execute("CALL dsdgen(sf=1)")
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    columns_by_table = {}
    for t in tables:
        cols = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position", [t]).fetchall()
        columns_by_table[t] = cols
        con.execute(f"COPY {t} TO '{PARQUET / (t + '.parquet')}' (FORMAT PARQUET)")
    duck = checksums(lambda q: con.execute(q).fetchone(), columns_by_table, "duckdb")
    con.close()
    return columns_by_table, duck


def ddl(columns_by_table):
    stmts = []
    for t, cols in columns_by_table.items():
        body = ",\n".join(f"  {c} {sf_type(ty)}" for c, ty in cols)
        stmts.append(f"CREATE OR REPLACE TABLE {t} (\n{body}\n);")
    return "\n\n".join(stmts) + "\n"


def load_snowflake(columns_by_table, ddl_text):
    from sf_connect import connect
    query_ids = {}
    with connect("loader") as con:
        cur = con.cursor()
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS SLSTUDY.{SCHEMA}")
        cur.execute(f"USE SCHEMA SLSTUDY.{SCHEMA}")
        for stmt in ddl_text.strip().split("\n\n"):
            cur.execute(stmt)
        for t in columns_by_table:
            cur.execute(f"PUT 'file://{PARQUET / (t + '.parquet')}' @%{t} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
            cur.execute(
                f"COPY INTO {t} FROM @%{t} FILE_FORMAT=(TYPE=PARQUET) "
                "MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE PURGE=TRUE")
            query_ids[t] = cur.sfqid
        snow = checksums(lambda q: cur.execute(q).fetchone(), columns_by_table, "snowflake")
    return snow, query_ids


def canonical(checks):
    # Snowflake and DuckDB print decimals with different trailing zeros.
    def norm(v):
        return None if v is None else format(Decimal(v).normalize(), "f")
    return {t: {"rows": c["rows"],
                "columns": {k: {"agg": norm(v["agg"]), "nulls": v["nulls"]} for k, v in c["columns"].items()}}
            for t, c in checks.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local-only", action="store_true")
    args = ap.parse_args()

    columns_by_table, duck = generate_and_export()
    ddl_text = ddl(columns_by_table)
    data_dir = STUDY / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "tpcds_sf1_ddl.sql").write_text(ddl_text)

    receipt = {
        "kind": "data preparation receipt, not a study result",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "generator": {"tool": "duckdb tpcds extension dsdgen", "duckdb": duckdb.__version__, "scale_factor": 1},
        "parquet_sha256": {t: sha256(PARQUET / (t + ".parquet")) for t in columns_by_table},
        "ddl_sha256": hashlib.sha256(ddl_text.encode()).hexdigest(),
        "duckdb_checksums": duck,
    }
    if args.local_only:
        receipt["snowflake"] = "not loaded (--local-only)"
        ok = True
    else:
        snow, query_ids = load_snowflake(columns_by_table, ddl_text)
        mismatches = []
        cd, cs = canonical(duck), canonical(snow)
        for t in cd:
            if cd[t]["rows"] != cs[t]["rows"]:
                mismatches.append(f"{t}: rows {cd[t]['rows']} vs {cs[t]['rows']}")
            for col in cd[t]["columns"]:
                if cd[t]["columns"][col] != cs[t]["columns"][col]:
                    mismatches.append(f"{t}.{col}: {cd[t]['columns'][col]} vs {cs[t]['columns'][col]}")
        receipt["snowflake"] = {"target": f"SLSTUDY.{SCHEMA}", "copy_query_ids": query_ids,
                                "checksums_match": not mismatches, "mismatches": mismatches}
        ok = not mismatches
    name = "TPCDS-SF1-LOCAL-RECEIPT.json" if args.local_only else "TPCDS-SF1-LOAD-RECEIPT.json"
    (data_dir / name).write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"{'OK' if ok else 'FAILED'}: {data_dir / name}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
