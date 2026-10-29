import pytest
from services.simulator import WhatIfEnergySimulator
from services.league_service import FairEfficiencyLeague
from config import Config
import pandas as pd

def test_tiered_tariff_calculation():
    sim = WhatIfEnergySimulator()
    sanctioned_load = Config.SANCTIONED_LOAD_KW
    fixed_charge = sanctioned_load * Config.FIXED_DEMAND_CHARGE_PER_KW # 120 * 120 = 14,400

    # Tier 1 only (e.g. 2000 kWh <= 3000 kWh):
    # Energy charge = 2000 * 7.50 = 15,000
    # Total = 14,400 + 15,000 = 29,400
    bill_tier1 = sim.calculate_bill(2000.0)
    assert bill_tier1 == 29400.0

    # Tier 2 (> 3000 kWh, e.g. 5000 kWh):
    # Tier 1 charge = 3000 * 7.50 = 22,500
    # Tier 2 charge = 2000 * 9.20 = 18,400
    # Fixed charge = 14,400
    # Total = 14,400 + 22,500 + 18,400 = 55,300
    bill_tier2 = sim.calculate_bill(5000.0)
    assert bill_tier2 == 55300.0

def test_carbon_emission_calculation():
    sim = WhatIfEnergySimulator()
    # 1000 kWh * 0.82 kg CO2/kWh = 820.0 kg
    co2 = sim.calculate_carbon_kg(1000.0)
    assert co2 == 820.0

def test_what_if_simulator_output():
    sim = WhatIfEnergySimulator()
    res = sim.simulate(
        current_monthly_kwh=18000.0,
        empty_room_cutoff_pct=50,
        led_retrofit_pct=50,
        fan_eco_regulation_pct=50,
        curfew_cutoff_enabled=True,
        geyser_timer_enabled=True,
        solar_pv_kwp=10.0
    )

    assert "baseline" in res
    assert "projected" in res
    assert "savings" in res
    assert res["savings"]["monthly_kwh"] > 0
    assert res["savings"]["monthly_cost_inr"] > 0
    assert res["savings"]["payback_months"] > 0
    assert res["projected"]["monthly_kwh"] < res["baseline"]["monthly_kwh"]

def test_fair_league_normalization():
    league = FairEfficiencyLeague()
    
    # Create mock dataset with Block-A (180 cap) and Block-C (240 cap)
    rows = []
    # Block A: 100 kWh, 150 occupants, 1 day
    rows.append({
        "timestamp": "2026-10-01 12:00:00",
        "block_id": "Block-A",
        "energy_kwh": 100.0,
        "power_kw": 10.0,
        "occupancy": 150,
        "occupancy_rate": 0.83,
        "temperature": 28.0,
        "humidity": 60.0,
        "day_type": "Weekday"
    })
    # Block C: 120 kWh, 220 occupants, 1 day
    # Note: Block C consumes more absolute kWh (120 vs 100), but has higher occupancy!
    rows.append({
        "timestamp": "2026-10-01 12:00:00",
        "block_id": "Block-C",
        "energy_kwh": 120.0,
        "power_kw": 12.0,
        "occupancy": 220,
        "occupancy_rate": 0.91,
        "temperature": 28.0,
        "humidity": 60.0,
        "day_type": "Weekday"
    })
    df = pd.DataFrame(rows)

    standings = league.compute_league_standings(df)
    assert len(standings) == 2
    
    # SEC for Block A: 100 / 150 = 0.67 kWh/occ-day
    # SEC for Block C: 120 / 220 = 0.55 kWh/occ-day (MORE efficient per occupant!)
    blk_c = next(s for s in standings if s["block_id"] == "Block-C")
    blk_a = next(s for s in standings if s["block_id"] == "Block-A")
    assert blk_c["sec_kwh_per_occ_day"] < blk_a["sec_kwh_per_occ_day"]
