"""Build the base (correct) Ossie layer and every per-question arm layer.

Input: the Ossie TPC-DS example at the pinned revision (ignored local clone) and
questions-v1.yaml. Output: layers/C1.yaml, layers/<QID>/{E,F1,F2}.yaml and
layers/MANIFEST.json (sha256 per file plus the inputs' hashes). Every output is
validated against Ossie's own JSON schema from the same revision.

All arms are produced by load -> edit -> the same dump, so formatting never
differs between arms; only content does.
"""
import copy
import hashlib
import itertools
import json
import pathlib
import sys

import jsonschema
import yaml

TASKS = pathlib.Path(__file__).resolve().parent
REPO = TASKS.parent
OSSIE = REPO / "local" / "slstudy-src" / "ossie"
OSSIE_REV = "2fd19c7a40b360bb87c18e8e0b7db482684b220a"
EXAMPLE = OSSIE / "examples" / "tpcds_semantic_model.yaml"
SCHEMA = OSSIE / "core-spec" / "ossie-schema.json"
VERSIONS = {"v1": ("questions-v1.yaml", "layers"), "v1.1": ("questions-v1.1.yaml", "layers-v1.1")}
TARGET_SCHEMA = "SLSTUDY.TPCDS_SF1"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def expr(e):
    return {"dialects": [{"dialect": "ANSI_SQL", "expression": e}]}


def field(name, e, desc, datatype, dimension=True, synonyms=None):
    f = {"name": name, "expression": expr(e)}
    if dimension:
        f["dimension"] = {"is_time": False}
    f["description"] = desc
    f["datatype"] = datatype
    if synonyms:
        f["ai_context"] = {"synonyms": synonyms}
    return f


def metric(name, e, desc, datatype, synonyms):
    return {"name": name, "expression": expr(e), "description": desc,
            "datatype": datatype, "ai_context": {"synonyms": synonyms}}


def find(model, ref):
    """Return (container list, element) for an element reference."""
    kind = ref["kind"]
    if kind == "metric":
        items = model["metrics"]
    elif kind == "relationship":
        items = model["relationships"]
    else:
        ds = next(d for d in model["datasets"] if d["name"] == ref["dataset"])
        items = ds["fields"] if kind == "field" else ds["metrics"]
    el = next(x for x in items if x["name"] == ref["name"])
    return items, el


def synonyms_of(el):
    ctx = el.setdefault("ai_context", {})
    return ctx.setdefault("synonyms", [])


# ---------------------------------------------------------------- base layer

def base_layer(example, version):
    m = copy.deepcopy(example)
    log = []

    for d in m["datasets"]:
        old = d["source"]
        d["source"] = f"{TARGET_SCHEMA}.{d['name']}"
        log.append(f"source {old} -> {d['source']}")
    m.pop("custom_extensions", None)
    log.append("removed model-level custom_extensions (Salesforce/dbt vendor metadata, irrelevant to the agents)")

    def describe(ref, text):
        _, el = find(m, ref)
        el["description"] = text
        log.append(f"description of {ref['name']} made explicit about its formula")

    describe({"kind": "metric", "name": "total_sales"},
             "Total sales revenue: sum of the extended sales price (quantity × unit sales price, before discounts and coupons) across all store sales transactions")
    describe({"kind": "metric", "name": "total_profit"},
             "Total net profit from store sales: net amount paid (after discounts and coupons, excluding tax) minus the extended wholesale cost")
    describe({"kind": "metric", "name": "customer_lifetime_value"},
             "Average sales value per distinct customer: total extended sales price of store purchases made by identified customers (sales with no customer are excluded) divided by the number of distinct customers")

    _, sp = find(m, {"kind": "metric", "name": "store_productivity"})
    sp["expression"] = expr("SUM(store_sales.ss_ext_sales_price) / NULLIF(MAX(store.s_number_employees), 0)")
    sp["description"] = "Sales per employee for one store: total extended sales price divided by the store's number of employees (requires grouping by store)"
    log.append("store_productivity fixed: the example divides by SUM(store.s_number_employees) over joined sales rows, "
               "which repeats the employee count once per sale (fan-out); now MAX per store group")

    _, q = find(m, {"kind": "field", "dataset": "date_dim", "name": "d_quarter_name"})
    synonyms_of(q).remove("fiscal quarter")
    log.append("removed synonym 'fiscal quarter' from d_quarter_name (calendar quarter; conflicts with the added fiscal_quarter)")
    _, npf = find(m, {"kind": "field", "dataset": "store_sales", "name": "ss_net_profit"})
    synonyms_of(npf).remove("margin")
    log.append("removed synonym 'margin' from ss_net_profit (a margin is usually a ratio; conflicts with the added gross_profit)")

    def add_fields(dataset, fields):
        ds = next(d for d in m["datasets"] if d["name"] == dataset)
        ds["fields"].extend(fields)
        log.append(f"added fields to {dataset}: {', '.join(f['name'] for f in fields)}")

    add_fields("store_sales", [
        field("ss_net_paid", "ss_net_paid", "Net amount paid after discounts and coupons, excluding tax", "Decimal", dimension=False),
        field("ss_net_paid_inc_tax", "ss_net_paid_inc_tax", "Net amount paid after discounts and coupons, including tax", "Decimal", dimension=False),
        field("ss_ext_wholesale_cost", "ss_ext_wholesale_cost", "Extended wholesale cost (quantity × unit wholesale cost)", "Decimal", dimension=False),
        field("ss_coupon_amt", "ss_coupon_amt", "Coupon amount applied to the sale line", "Decimal", dimension=False),
    ])
    add_fields("date_dim", [
        field("fiscal_year", "CASE WHEN d_moy >= 2 THEN d_year ELSE d_year - 1 END",
              "Fiscal year. The fiscal year starts on 1 February and is named for the calendar year in which it starts (FY2000 runs from 1 February 2000 to 31 January 2001)",
              "Integer", synonyms=["fiscal year", "FY"]),
        field("fiscal_quarter", "FLOOR(MOD(d_moy + 10, 12) / 3) + 1",
              "Fiscal quarter (1-4) within the fiscal year; Q1 is February to April",
              "Integer", synonyms=["fiscal quarter"]),
        (field("is_weekend", "d_weekend = 'Y'",
               "True when the date falls on a weekend (source flag d_weekend = 'Y')",
               "Boolean", synonyms=["weekend"]) if version == "v1" else
         field("is_weekend", "d_day_name IN ('Saturday', 'Sunday')",
               "True when the date falls on a Saturday or Sunday",
               "Boolean", synonyms=["weekend"])),
    ])
    add_fields("customer", [
        field("c_birth_year", "c_birth_year", "Customer's year of birth", "Integer", synonyms=["birth year"]),
        field("is_preferred_customer", "c_preferred_cust_flag = 'Y'",
              "True when the customer is enrolled in the preferred-customer program (source flag c_preferred_cust_flag = 'Y')",
              "Boolean", synonyms=["preferred customer", "preferred"]),
    ])
    add_fields("item", [
        field("i_class", "i_class", "Item class within a category", "String", synonyms=["item class", "class"]),
        field("is_apparel", "i_category IN ('Men', 'Women', 'Children')",
              "True for apparel items, defined as the Men, Women and Children categories",
              "Boolean", synonyms=["apparel", "clothing"]),
    ])
    add_fields("store", [
        field("store_size_class", "CASE WHEN s_number_employees >= 270 THEN 'large' ELSE 'standard' END",
              "Store size class: 'large' when the store has at least 270 employees, otherwise 'standard'",
              "String", synonyms=["store size", "large store"]),
    ])

    new_metrics = [
        metric("net_sales", "SUM(store_sales.ss_net_paid)",
               "Net sales: net amount paid after discounts and coupons, excluding tax",
               "Decimal", ["net revenue", "sales after discounts"]),
        metric("gross_profit", "SUM(store_sales.ss_ext_sales_price - store_sales.ss_ext_wholesale_cost)",
               "Gross profit: extended sales price minus extended wholesale cost, before discounts and coupons",
               "Decimal", ["gross margin dollars", "profit before discounts"]),
        metric("average_ticket_value", "SUM(store_sales.ss_ext_sales_price) / COUNT(DISTINCT store_sales.ss_ticket_number)",
               "Average value of a sales ticket: total extended sales price divided by the number of distinct tickets",
               "Decimal", ["average basket value", "average transaction value"]),
        metric("distinct_customers", "COUNT(DISTINCT store_sales.ss_customer_sk)",
               "Number of distinct identified customers with at least one store purchase",
               "Integer", ["unique customers", "customer count"]),
    ]
    m["metrics"].extend(new_metrics)
    log.append("added metrics: " + ", ".join(x["name"] for x in new_metrics))

    for name, text in [
        ("store_sales_to_customer", "Each sale links to the purchasing customer: store_sales.ss_customer_sk = customer.c_customer_sk."),
        ("store_sales_to_store", "Each sale links to the store where it took place: store_sales.ss_store_sk = store.s_store_sk."),
    ]:
        _, rel = find(m, {"kind": "relationship", "name": name})
        rel.setdefault("ai_context", {})["instructions"] = text
        log.append(f"added ai_context.instructions to relationship {name} (the schema has no relationship description)")
    return m, log


# ---------------------------------------------------------------- arms

def apply_fault(base, fault, with_descriptions):
    m = copy.deepcopy(base)
    for e in fault:
        if e["kind"] == "synonym":
            _, src = find(m, e["from"])
            _, dst = find(m, e["to"])
            synonyms_of(src).remove(e["synonym"])
            synonyms_of(dst).append(e["synonym"])
            if with_descriptions:
                if "f1_to_description" in e:
                    dst["description"] = e["f1_to_description"]
                if "f1_from_description" in e:
                    src["description"] = e["f1_from_description"]
            continue
        _, el = find(m, e)
        if "expression" in e:
            el["expression"] = expr(e["expression"])
        for k in ("from_columns", "to_columns"):
            if k in e:
                el[k] = list(e[k])
        if with_descriptions:
            if "f1_description" in e:
                el["description"] = e["f1_description"]
            if "f1_instructions" in e:
                el["ai_context"]["instructions"] = e["f1_instructions"]
    return m


def remove_elements(base, removals):
    m = copy.deepcopy(base)
    for r in removals:
        if r["kind"] == "synonym":
            _, owner = find(m, r["owner"])
            synonyms_of(owner).remove(r["synonym"])
        else:
            items, el = find(m, r)
            items.remove(el)
    return m


def without_metrics(base):
    """Arm C1a: the correct layer with every metric (model-level and dataset-level) removed."""
    m = copy.deepcopy(base)
    m.pop("metrics", None)
    for d in m["datasets"]:
        d.pop("metrics", None)
    return m


def without_descriptions(base):
    """Arm C1b: the correct layer with every description and ai_context removed (structure and expressions only)."""
    def strip(node):
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k not in ("description", "ai_context")}
        if isinstance(node, list):
            return [strip(x) for x in node]
        return node
    return strip(copy.deepcopy(base))


def dump(model):
    return yaml.safe_dump(model, sort_keys=False, allow_unicode=True, width=1000).encode()


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    qfile, outdir = VERSIONS[version]
    OUT = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else TASKS / outdir
    example_bytes = EXAMPLE.read_bytes()
    schema = json.loads(SCHEMA.read_text())
    validator = jsonschema.validators.validator_for(schema)(schema)
    spec_bytes = (TASKS / qfile).read_bytes()
    questions = yaml.safe_load(spec_bytes)["questions"]

    base, log = base_layer(yaml.safe_load(example_bytes), version)
    if version != "v1":
        log.append("v1.1: is_weekend defined by day name (Saturday, Sunday); in TPC-DS SF1 the source flag "
                   "d_weekend = 'Y' marks Fridays and Saturdays (post-pilot amendment 01)")
    outputs = {"C1.yaml": dump(base), "C1a.yaml": dump(without_metrics(base)), "C1b.yaml": dump(without_descriptions(base))}
    for q in questions:
        qid = q["id"]
        outputs[f"{qid}/E.yaml"] = dump(remove_elements(base, q["remove"]))
        outputs[f"{qid}/F2.yaml"] = dump(apply_fault(base, q["fault"], with_descriptions=False))
        outputs[f"{qid}/F1.yaml"] = dump(apply_fault(base, q["fault"], with_descriptions=True))

    problems = []
    for path, data in outputs.items():
        errors = sorted(validator.iter_errors(yaml.safe_load(data)), key=str)
        if errors:
            problems.append(f"{path}: schema: {errors[0].message[:200]}")
    for q in questions:
        arms = {a: outputs[f"{q['id']}/{a}.yaml"] for a in ("E", "F1", "F2")}
        for a, b in itertools.combinations(["C1", "E", "F1", "F2"], 2):
            da = outputs["C1.yaml"] if a == "C1" else arms[a]
            db = outputs["C1.yaml"] if b == "C1" else arms[b]
            if da == db:
                problems.append(f"{q['id']}: arms {a} and {b} are identical")

    OUT.mkdir(exist_ok=True)
    for path, data in outputs.items():
        (OUT / path).parent.mkdir(parents=True, exist_ok=True)
        (OUT / path).write_bytes(data)
    manifest = {
        "kind": f"generated task material, question set {version}",
        "inputs": {
            "ossie_revision": OSSIE_REV,
            "example_sha256": sha(example_bytes),
            "schema_sha256": sha(SCHEMA.read_bytes()),
            "questions_sha256": sha(spec_bytes),
            "builder_sha256": sha(pathlib.Path(__file__).read_bytes()),
        },
        "base_layer_edits": log,
        "files": {p: sha(d) for p, d in sorted(outputs.items())},
        "schema_valid_and_distinct": not problems,
        "problems": problems,
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{len(outputs)} layer files; problems: {len(problems)}")
    for p in problems:
        print("  ", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
