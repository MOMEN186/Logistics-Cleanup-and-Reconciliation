import csv
import json
import re
from datetime import datetime
from pathlib import Path


# ----------------------------
# Helpers
# ----------------------------
def normalize_keys(obj):
    """Recursively lowercase all dict keys."""
    if isinstance(obj, dict):
        return {str(k).lower(): normalize_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_keys(x) for x in obj]
    return obj


def load_zones_csv(path: Path):
    """
    Returns a dict mapping lowercase raw zone -> canonical zone.
    CSV format: raw,canonical
    """
    mapping = {}
    with path.open("r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            raw = (row.get("raw") or "").strip().lower()
            canonical = (row.get("canonical") or "").strip()
            if raw:
                mapping[raw] = canonical or row.get("raw", "")
    return mapping


def normalize_orders(orders, zones_map):
    """
    Normalize incoming orders:
      - keys -> lowercase
      - city -> canonical via zones_map (case-insensitive)
      - keep fields if present: orderid, city, paymenttype, producttype, weight, deadline, address
    Returns list of normalized order dicts (lowercase keys).
    """
    normalized = []
    orders = normalize_keys(orders)
    for o in orders:
        order_id = (o.get("orderid") or o.get("order_id") or o.get("order") or "").strip()
        city_raw = (o.get("city") or "").strip()
        city = zones_map.get(city_raw.lower(), city_raw)
        payment_type = (o.get("paymenttype") or "").strip() or (o.get("payment") or "").strip()
        product_type = (o.get("producttype") or "").strip()
        weight = o.get("weight", 0)
        deadline = (o.get("deadline") or "").strip()
        address = (o.get("address") or "").strip()

        normalized.append({
            "orderid": order_id,
            "city": city,
            "paymenttype": payment_type,
            "producttype": product_type,
            "weight": weight,
            "deadline": deadline,
            "address": address
        })
    return normalized


def dedup(orders):
    """
    De-duplicate orders by orderid.
    - If multiple entries with same orderid & different address -> keep first and add warning.
    - Always keep first occurrence.
    Returns (clean_orders, warnings)
    """
    seen = {}
    warnings = []
    for o in orders:
        oid = o["orderid"]
        if oid not in seen:
            seen[oid] = o
        else:
            # conflict if address differs and both non-empty
            if o.get("address") and seen[oid].get("address") and o["address"] != seen[oid]["address"]:
                warnings.append(f"Conflicting address for order {oid}")
            # ignore subsequent duplicates (keep first)
    return list(seen.values()), warnings


# ----------------------------
# Planning
# ----------------------------
def plan_assignments(orders, couriers):
    """
    Assign orders to couriers with these rules:
      1) Must cover the order's city.
      2) If payment is COD, courier must accept COD.
      3) Product type must not be excluded.
      4) Capacity must not be exceeded.
      5) Among eligible couriers, choose the one with the **lowest current load**,
         breaking ties by courier priority (lower number = higher priority).
    Returns: (assignments, unassigned, capacity_usage, unassigned_reasons)
    """
    orders = normalize_keys(orders)
    couriers = normalize_keys(couriers)

    assignments = []
    unassigned = []
    unassigned_reasons = {}

    capacity_usage = {c["courierid"]: 0 for c in couriers}

    # Couriers sorted by priority for tie-breaking
    couriers_sorted = sorted(couriers, key=lambda c: c.get("priority", 10**9))

    for o in orders:
        oid = o["orderid"]
        city = o.get("city", "")
        payment = (o.get("paymenttype") or "").lower()
        product = (o.get("producttype") or "").lower()
        weight = float(o.get("weight") or 0)

        # Build filters progressively so we can set a precise unassigned reason.
        in_zone = [c for c in couriers_sorted if city in c.get("zonescovered", [])]
        if not in_zone:
            unassigned.append(oid)
            unassigned_reasons[oid] = "Zone not covered"
            continue

        cod_ok = [c for c in in_zone if (payment != "cod") or c.get("acceptscod", False)]
        if payment == "cod" and not cod_ok:
            unassigned.append(oid)
            unassigned_reasons[oid] = "COD not accepted"
            continue

        excl_ok = [
            c for c in cod_ok
            if product not in [str(e).lower() for e in c.get("exclusions", [])]
        ]
        if not excl_ok:
            unassigned.append(oid)
            unassigned_reasons[oid] = f"Excluded product type: {o.get('producttype', '')}"
            continue

        cap_ok = [
            c for c in excl_ok
            if capacity_usage[c["courierid"]] + weight <= float(c.get("dailycapacity") or 0)
        ]
        if not cap_ok:
            unassigned.append(oid)
            unassigned_reasons[oid] = "Capacity exceeded"
            continue

        # Choose least-used courier; tie-break by priority
        chosen = sorted(
            cap_ok,
            key=lambda c: (capacity_usage[c["courierid"]], c.get("priority", 10**9))
        )[0]

        assignments.append({
            "orderId": oid,                   # camelCase in output
            "courierId": chosen["courierid"]  # camelCase in output
        })
        capacity_usage[chosen["courierid"]] += weight

    return assignments, unassigned, capacity_usage, unassigned_reasons


# ----------------------------
# Reconciliation
# ----------------------------
def reconcile(assignments, orders, log_rows, couriers):
    """
    Build reconciliation report:
      - unexpected: scanned orders not in orders list
      - misassigned: scanned by different courier than planned
      - late: scan after order deadline (if provided)
      - duplicate: same order scanned multiple times
      - notDelivered: orders never scanned
    """
    # Lowercase internal view
    orders_l = normalize_keys(orders)
    log_l = normalize_keys(log_rows)
    assignments_l = normalize_keys(assignments)

    order_ids = {o["orderid"] for o in orders_l if o.get("orderid")}
    planned_by_order = {a["orderid"]: a["courierid"] for a in assignments_l}

    delivered_orders = set()
    unexpected = []
    misassigned = []
    late = []
    duplicate = []
    seen_scan = set()

    for row in log_l:
        oid = re.sub(r"[^A-Za-z0-9-]", "", (row.get("orderid") or "").upper().strip())
        cid = (row.get("courierid") or "").strip()
        ts = (row.get("deliveredat") or "").strip()

        if not oid:
            continue

        # unexpected
        if oid not in order_ids:
            unexpected.append(oid)

        # duplicate
        if oid in seen_scan:
            duplicate.append(oid)
        else:
            seen_scan.add(oid)

        delivered_orders.add(oid)

        # misassigned
        planned_cid = planned_by_order.get(oid)
        if planned_cid and planned_cid != cid:
            misassigned.append(oid)

        # late
        order = next((o for o in orders_l if o["orderid"] == oid), None)
        if order and order.get("deadline") and ts:
            try:
                d_deadline = datetime.strptime(order["deadline"], "%Y-%m-%d %H:%M")
                d_delivered = datetime.strptime(ts, "%Y-%m-%d %H:%M")
                if d_delivered > d_deadline:
                    late.append(oid)
            except ValueError:
                pass  # ignore unparsable dates

    not_delivered = sorted(oid for oid in order_ids if oid not in delivered_orders)

    return {
        "unexpected": sorted(set(unexpected)),
        "misassigned": sorted(set(misassigned)),
        "late": sorted(set(late)),
        "duplicate": sorted(set(duplicate)),
        "notDelivered": not_delivered
    }


# ----------------------------
# I/O & Main
# ----------------------------
def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_log_csv(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            rows.append(row)
    return rows


def main():
    cwd = Path(".")
    orders_raw = read_json(cwd / "orders.json")
    couriers_raw = read_json(cwd / "couriers.json")
    zones_map = load_zones_csv(cwd / "zones.csv")
    log_rows = read_log_csv(cwd / "log.csv")

    # Normalize + dedup orders
    orders_norm = normalize_orders(orders_raw, zones_map)
    orders_clean, warnings = dedup(orders_norm)

    # Plan
    assignments, unassigned, capacity_usage, unassigned_reasons = plan_assignments(
        orders_clean, couriers_raw
    )

    # Reconcile
    reconciliation = reconcile(assignments, orders_clean, log_rows, couriers_raw)

    # Write outputs
    (cwd / "clean_orders.json").write_text(
        json.dumps({"orders": orders_clean, "warnings": warnings}, indent=2),
        encoding="utf-8"
    )

    (cwd / "plan.json").write_text(
        json.dumps({
            "assignments": assignments,
            "unassigned": unassigned,
            "capacityUsage": capacity_usage,
            "unassignedReasons": unassigned_reasons
        }, indent=2),
        encoding="utf-8"
    )

    (cwd / "reconciliation.json").write_text(
        json.dumps(reconciliation, indent=2),
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
