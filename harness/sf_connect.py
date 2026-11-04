"""Key-pair Snowflake connections for the semantic-layer study.

Account details and private keys live in the ignored local/snowflake-slstudy/
directory; nothing secret is read from or written to the study tree.
"""
import json
import pathlib

import snowflake.connector
from cryptography.hazmat.primitives import serialization

REPO = pathlib.Path(__file__).resolve().parents[1]
LOCAL = REPO / "local" / "snowflake-slstudy"

PROFILES = {
    # Executes agent-written SQL. SELECT only, 120 s statement cap.
    "ro": {"user_key": "ro_user", "key_key": "ro_private_key", "role": "SLSTUDY_RO"},
    # Loads study tables. Never used by the executor.
    "loader": {"user_key": "loader_user", "key_key": "loader_private_key", "role": "SLSTUDY_LOADER"},
}


def account():
    return json.loads((LOCAL / "ACCOUNT.json").read_text())


def connect(profile, database="SLSTUDY", schema=None):
    acct = account()
    p = PROFILES[profile]
    pem = (REPO / acct[p["key_key"]]).read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    der = key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        account=acct["account_identifier"],
        user=acct[p["user_key"]],
        private_key=der,
        role=p["role"],
        warehouse="SLSTUDY_WH",
        database=database,
        schema=schema,
        session_parameters={"QUERY_TAG": f"slstudy-{profile}"},
    )
