from main import normalize_orders, dedup, plan_assignments,reconcile
import json
from tests.utils import run_main_in_dir, load_json

def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_normalize_orders_zone_mapping():
    orders = [
        {"orderId": "1", "city": "6 October", "paymentType": "COD",
         "productType": "standard", "weight": 1, "deadline": "2025-08-12 10:00"}
    ]
    zones = {"6 october": "6th of October"}

    result = normalize_orders(orders, zones)
    assert result[0]["city"] == "6th of October"
    assert result[0]["paymenttype"] == "COD"
    assert result[0]["producttype"] == "standard"
    assert result[0]["weight"] == 1


def test_dedup_conflicting_addresses():
    orders = [
        {"orderid": "A1", "address": "123 Main St"},
        {"orderid": "A1", "address": "456 Side Ave"}
    ]
    cleaned, warnings = dedup(orders)
    assert len(cleaned) == 1
    assert any("Conflicting" in w for w in warnings)


def test_plan_assignments_respects_exclusions_and_priority():
    orders = [
        {"orderid": "A", "city": "Giza", "paymenttype": "COD",
         "producttype": "fragile", "weight": 5},
        {"orderid": "B", "city": "Giza", "paymenttype": "COD",
         "producttype": "standard", "weight": 1}
    ]
    couriers = [
        {"courierid": "C1", "zonescovered": ["Giza"], "acceptscod": True,
         "dailycapacity": 10, "priority": 1, "exclusions": ["fragile"]},
        {"courierid": "C2", "zonescovered": ["Giza"], "acceptscod": True,
         "dailycapacity": 10, "priority": 2, "exclusions": []}
    ]
    assignments, unassigned, usage, _ = plan_assignments(orders, couriers)

    assign_map = {a["orderId"]: a["courierId"] for a in assignments}
    assert assign_map["A"] == "C2"
    assert assign_map["B"] == "C1"
    assert unassigned == []


def test_plan_assignments_respects_capacity():
    orders = [
        {"orderid": "A", "city": "Giza", "paymenttype": "COD",
         "producttype": "standard", "weight": 7},
        {"orderid": "B", "city": "Giza", "paymenttype": "COD",
         "producttype": "standard", "weight": 5}
    ]
    couriers = [
        {"courierid": "C1", "zonescovered": ["Giza"], "acceptscod": True,
         "dailycapacity": 10, "priority": 1, "exclusions": []}
    ]
    assignments, unassigned, usage, _ = plan_assignments(orders, couriers)

    assert len(assignments) == 1
    assert len(unassigned) == 1
    assert usage["C1"] <= 10


def test_plan_assignments_unassigned_reasons():
    orders = [
        {"orderid": "A", "city": "Alex", "paymenttype": "COD",
         "producttype": "standard", "weight": 1},
        {"orderid": "B", "city": "Giza", "paymenttype": "COD",
         "producttype": "fragile", "weight": 1}
    ]
    couriers = [
        {"courierid": "C1", "zonescovered": ["Giza"], "acceptscod": True,
         "dailycapacity": 10, "priority": 1, "exclusions": ["fragile"]}
    ]
    _, unassigned, _, reasons = plan_assignments(orders, couriers)

    assert "A" in unassigned
    assert reasons["A"] == "Zone not covered"
    assert "B" in unassigned
    assert reasons["B"] == "Excluded product type: fragile"


def test_reconcile_includes_not_delivered():
    assignments = [
        {"orderId": "A", "courierId": "C1"},
        {"orderId": "B", "courierId": "C1"}
    ]
    orders = [
        {"orderid": "A", "deadline": "2025-08-12 10:00"},
        {"orderid": "B", "deadline": "2025-08-12 10:00"}
    ]
    log = [
        {"orderid": "A", "courierid": "C1", "deliveredat": "2025-08-12 09:00"}
    ]
    couriers = [{"courierid": "C1"}]

    result = reconcile(assignments, orders, log, couriers)
    assert "notDelivered" in result
    assert result["notDelivered"] == ["B"]


def test_reconciliation_json_contains_not_delivered(temp_dir):
    # Prepare minimal input files
    write_file(temp_dir / "orders.json", json.dumps([
        {"orderId": "A", "city": "Giza", "paymentType": "COD", "productType": "standard",
         "weight": 1, "deadline": "2025-08-12 10:00"},
        {"orderId": "B", "city": "Giza", "paymentType": "COD", "productType": "standard",
         "weight": 1, "deadline": "2025-08-12 10:00"}
    ], indent=2))

    write_file(temp_dir / "couriers.json", json.dumps([
        {"courierId": "Weevo", "zonesCovered": ["Giza"], "acceptsCOD": True,
         "dailyCapacity": 10, "priority": 1, "exclusions": []}
    ], indent=2))

    write_file(temp_dir / "zones.csv", "raw,canonical\nGiza,Giza\n")

    # Log only contains a scan for order A
    write_file(temp_dir / "log.csv", "orderId,courierId,deliveredAt\nA,Weevo,2025-08-12 09:00\n")

    # Run the main script inside the temp dir
    run_main_in_dir(temp_dir)

    # Load reconciliation.json
    reconciliation = load_json(temp_dir, "reconciliation.json")

    # Assertions
    assert "notDelivered" in reconciliation, "'notDelivered' key missing in reconciliation.json"
    assert reconciliation["notDelivered"] == ["B"], "Order B should be marked as not delivered"
