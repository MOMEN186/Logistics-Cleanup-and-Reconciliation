import json
import subprocess
import shutil
import tempfile
from pathlib import Path
import pytest
from tests.utils import write_file, run_main_in_dir, load_json


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d)

# ------------------------------
# Test 1: Misassigned & Late
# ------------------------------
def test_misassigned_and_late(temp_dir):
    write_file(temp_dir / "orders.json", json.dumps([
        {"orderId": "ORD-001", "city": "6 October", "paymentType": "COD", "productType": "fragile", "weight": 1, "deadline": "2025-08-12 16:30"},
        {"orderId": "ORD-002", "city": "6 October", "paymentType": "COD", "productType": "standard", "weight": 1, "deadline": "2025-08-12 16:30"}
    ], indent=2))

    write_file(temp_dir / "couriers.json", json.dumps([
        {"courierId": "Weevo", "zonesCovered": ["6th of October"], "acceptsCOD": True, "dailyCapacity": 10, "priority": 1, "exclusions": []},
        {"courierId": "Bosta", "zonesCovered": ["6th of October"], "acceptsCOD": True, "dailyCapacity": 10, "priority": 2, "exclusions": ["fragile"]}
    ], indent=2))

    write_file(temp_dir / "zones.csv", "raw,canonical\n6 October,6th of October\n6th of Oct.,6th of October\n")

    write_file(temp_dir / "log.csv", "orderId,courierId,deliveredAt\nORD-001,Bosta,2025-08-12 16:31\nORD-002,Weevo,2025-08-12 16:25\nORD-999,Weevo,2025-08-12 16:20\n")

    run_main_in_dir(temp_dir)
    rec = load_json(temp_dir, "reconciliation.json")

    assert "ORD-999" in rec["unexpected"]
    assert "ORD-001" in rec["late"]
    assert "ORD-001" in rec["misassigned"]


# ------------------------------
# Test 2: Capacity & Exclusions
# ------------------------------
def test_capacity_and_exclusions(temp_dir):
    write_file(temp_dir / "orders.json", json.dumps([
        {"orderId": "A", "city": "Giza", "paymentType": "COD", "productType": "fragile", "weight": 5, "deadline": "2025-08-12 10:00"},
        {"orderId": "B", "city": "Dokki", "paymentType": "COD", "productType": "standard", "weight": 3, "deadline": "2025-08-12 11:00"},
        {"orderId": "C", "city": "Dokki", "paymentType": "Prepaid", "productType": "standard", "weight": 2, "deadline": "2025-08-12 12:00"}
    ], indent=2))

    write_file(temp_dir / "couriers.json", json.dumps([
        {"courierId": "Weevo", "zonesCovered": ["Giza", "Dokki"], "acceptsCOD": True, "dailyCapacity": 10, "priority": 1, "exclusions": []},
        {"courierId": "Bosta", "zonesCovered": ["Giza", "Dokki"], "acceptsCOD": True, "dailyCapacity": 10, "priority": 2, "exclusions": ["fragile"]},
        {"courierId": "SafeShip", "zonesCovered": ["Dokki"], "acceptsCOD": False, "dailyCapacity": 10, "priority": 3, "exclusions": []}
    ], indent=2))

    write_file(temp_dir / "zones.csv", "raw,canonical\nGiza,Giza\nDokki,Dokki\n")

    write_file(temp_dir / "log.csv", "orderId,courierId,deliveredAt\n")

    run_main_in_dir(temp_dir)
    plan = load_json(temp_dir, "plan.json")

    assign_map = {a["orderId"]: a["courierId"] for a in plan["assignments"]}
    assert assign_map["A"] == "Weevo"
    assert assign_map["B"] == "Bosta"
    assert assign_map["C"] == "SafeShip"


# ------------------------------
# Test 3: Duplicate Scans
# ------------------------------
def test_duplicate_scans(temp_dir):
    write_file(temp_dir / "orders.json", json.dumps([
        {"orderId": "ORD-002", "city": "Giza", "paymentType": "COD", "productType": "standard", "weight": 1, "deadline": "2025-08-12 10:00"}
    ], indent=2))

    write_file(temp_dir / "couriers.json", json.dumps([
        {"courierId": "Weevo", "zonesCovered": ["Giza"], "acceptsCOD": True, "dailyCapacity": 10, "priority": 1, "exclusions": []}
    ], indent=2))

    write_file(temp_dir / "zones.csv", "raw,canonical\nGiza,Giza\n")

    write_file(temp_dir / "log.csv", "orderId,courierId,deliveredAt\nORD-002,Weevo,2025-08-12 09:00\nORD-002,Weevo,2025-08-12 09:05\n")

    run_main_in_dir(temp_dir)
    rec = load_json(temp_dir, "reconciliation.json")

    assert "ORD-002" in rec["duplicate"]


# ------------------------------
# Test 4: Zone Normalization
# ------------------------------
def test_zone_normalization(temp_dir):
    write_file(temp_dir / "orders.json", json.dumps([
        {"orderId": "Z1", "city": "6 October", "paymentType": "COD", "productType": "standard", "weight": 1, "deadline": "2025-08-12 10:00"},
        {"orderId": "Z2", "city": "6th of Oct.", "paymentType": "COD", "productType": "standard", "weight": 1, "deadline": "2025-08-12 10:00"},
        {"orderId": "Z3", "city": "6th of October", "paymentType": "COD", "productType": "standard", "weight": 1, "deadline": "2025-08-12 10:00"}
    ], indent=2))

    write_file(temp_dir / "couriers.json", json.dumps([
        {"courierId": "Weevo", "zonesCovered": ["6th of October"], "acceptsCOD": True, "dailyCapacity": 10, "priority": 1, "exclusions": []}
    ], indent=2))

    write_file(temp_dir / "zones.csv", "raw,canonical\n6 October,6th of October\n6th of Oct.,6th of October\n6th of October,6th of October\n")

    write_file(temp_dir / "log.csv", "orderId,courierId,deliveredAt\n")

    run_main_in_dir(temp_dir)
    clean = load_json(temp_dir, "clean_orders.json")

    cities = {o["city"] for o in clean["orders"]}
    assert cities == {"6th of October"}


# ------------------------------
# Test 5: Conflicting Addresses
# ------------------------------
def test_conflicting_addresses_warning(temp_dir):
    write_file(temp_dir / "orders.json", json.dumps([
        {"orderId": "ORD-050", "city": "Giza", "address": "123 Main St", "paymentType": "COD", "productType": "standard", "weight": 1, "deadline": "2025-08-12 10:00"},
        {"orderId": "ORD-050", "city": "Giza", "address": "456 Side Ave", "paymentType": "COD", "productType": "standard", "weight": 1, "deadline": "2025-08-12 10:00"}
    ], indent=2))

    write_file(temp_dir / "couriers.json", json.dumps([
        {"courierId": "Weevo", "zonesCovered": ["Giza"], "acceptsCOD": True, "dailyCapacity": 10, "priority": 1, "exclusions": []}
    ], indent=2))

    write_file(temp_dir / "zones.csv", "raw,canonical\nGiza,Giza\n")

    write_file(temp_dir / "log.csv", "orderId,courierId,deliveredAt\n")

    run_main_in_dir(temp_dir)
    clean = load_json(temp_dir, "clean_orders.json")

    assert "warnings" in clean
    assert any("Conflicting" in w for w in clean["warnings"])

def test_plan_json_contains_unassigned_reasons(temp_dir):
    # Prepare input files
    write_file(temp_dir / "orders.json", json.dumps([
        {"orderId": "A", "city": "Alex", "paymentType": "COD", "productType": "standard", "weight": 1},
        {"orderId": "B", "city": "Giza", "paymentType": "COD", "productType": "fragile", "weight": 1}
    ], indent=2))

    write_file(temp_dir / "couriers.json", json.dumps([
        {"courierId": "C1", "zonesCovered": ["Giza"], "acceptsCOD": True,
         "dailyCapacity": 10, "priority": 1, "exclusions": ["fragile"]}
    ], indent=2))

    write_file(temp_dir / "zones.csv", "raw,canonical\nGiza,Giza\nAlex,Alex\n")

    write_file(temp_dir / "log.csv", "orderId,courierId,deliveredAt\n")

    # Run the main program in the temp_dir
    run_main_in_dir(temp_dir)

    # Load and check plan.json
    plan = load_json(temp_dir, "plan.json")
    assert "unassignedReasons" in plan, "plan.json must contain 'unassignedReasons' key"

    # Validate the reasons match expected
    reasons = plan["unassignedReasons"]
    assert reasons["A"] == "Zone not covered"
    assert reasons["B"] == "Excluded product type: fragile"


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
