import numpy as np
import pandas as pd
from config import Config

class WhatIfEnergySimulator:
    """
    What-If Energy Simulator:
    Simulates the quantitative impact of energy conservation measures (ECMs)
    on hostel power demand, electricity bills (tiered tariffs), and carbon footprint.
    """
    def __init__(self, tariff_tier1=Config.TARIFF_TIER_1_RATE,
                 tariff_tier2=Config.TARIFF_TIER_2_RATE,
                 emission_factor=Config.GRID_EMISSION_FACTOR_KG_CO2_PER_KWH):
        self.tariff_tier1 = tariff_tier1
        self.tariff_tier2 = tariff_tier2
        self.tier1_limit = Config.TARIFF_TIER_1_LIMIT_KWH
        self.emission_factor = emission_factor

    def calculate_bill(self, kwh_month, sanctioned_kw=Config.SANCTIONED_LOAD_KW):
        """Calculates electricity bill based on institutional two-part tiered tariff."""
        fixed_charge = sanctioned_kw * Config.FIXED_DEMAND_CHARGE_PER_KW
        if kwh_month <= self.tier1_limit:
            energy_charge = kwh_month * self.tariff_tier1
        else:
            energy_charge = (self.tier1_limit * self.tariff_tier1) + ((kwh_month - self.tier1_limit) * self.tariff_tier2)
        return round(fixed_charge + energy_charge, 2)

    def calculate_carbon_kg(self, kwh):
        """Calculates carbon footprint in kg CO2e."""
        return round(kwh * self.emission_factor, 2)

    def simulate(self, current_monthly_kwh=18500.0,
                 empty_room_cutoff_pct=50,       # 0 - 100% compliance
                 led_retrofit_pct=60,           # 0 - 100% fixtures
                 fan_eco_regulation_pct=70,     # 0 - 100% ESP32 coverage
                 curfew_cutoff_enabled=True,    # Night common room cut-off
                 geyser_timer_enabled=True,     # Hot water scheduling
                 solar_pv_kwp=15.0):            # Solar array size in kWp
        """
        Runs full simulation of combined ECMs and returns verified delta projections.
        """
        # Baseline disaggregation shares (approximate hostel campus distribution)
        # Lighting: 18%, Cooling/Fans: 32%, Plug/Electronics: 20%, Base Standby: 16%, Geysers/Spikes: 14%
        share_lighting = 0.18
        share_fans = 0.32
        share_empty_waste = 0.12 # Waste from lights/fans left on in unoccupied rooms
        share_geyser_standby = 0.08
        share_night_common_waste = 0.06

        kwh_savings_components = {}

        # 1. Empty Room Cutoff (Saves portion of empty room daytime waste)
        saving_empty = current_monthly_kwh * share_empty_waste * (empty_room_cutoff_pct / 100.0) * 0.75
        kwh_savings_components["empty_room_cutoff"] = {
            "name": "Vacant Room Smart Cutoff",
            "kwh_saved": round(saving_empty, 1),
            "description": f"{empty_room_cutoff_pct}% automated or prefect shutdown during empty class hours"
        }

        # 2. LED Retrofit (Saves ~45% of retrofitted lighting energy)
        saving_led = current_monthly_kwh * share_lighting * (led_retrofit_pct / 100.0) * 0.45
        kwh_savings_components["led_retrofit"] = {
            "name": "Corridor & Room LED Retrofit",
            "kwh_saved": round(saving_led, 1),
            "description": f"{led_retrofit_pct}% conversion from T8 fluorescents to 18W smart LEDs"
        }

        # 3. ESP32 Fan Eco-Regulation (Saves ~28% of fan load via duty cycle & temperature control)
        saving_fans = current_monthly_kwh * share_fans * (fan_eco_regulation_pct / 100.0) * 0.28
        kwh_savings_components["fan_eco_regulation"] = {
            "name": "ESP32 Adaptive Fan Control",
            "kwh_saved": round(saving_fans, 1),
            "description": f"{fan_eco_regulation_pct}% coverage with automated thermal-speed control"
        }

        # 4. Curfew HVAC & Common Area Cutoff
        saving_curfew = (current_monthly_kwh * share_night_common_waste * 0.65) if curfew_cutoff_enabled else 0.0
        kwh_savings_components["curfew_cutoff"] = {
            "name": "Night Curfew Common Area Shutdown",
            "kwh_saved": round(saving_curfew, 1),
            "description": "Automated shutdown of study halls and TV lounges between 01:00 - 05:30 AM"
        }

        # 5. Geyser Timer Automation
        saving_geyser = (current_monthly_kwh * share_geyser_standby * 0.55) if geyser_timer_enabled else 0.0
        kwh_savings_components["geyser_automation"] = {
            "name": "Geyser Timer & Heat Scheduling",
            "kwh_saved": round(saving_geyser, 1),
            "description": "Restricting water heater operation to 05:30-09:00 AM avoids round-the-clock reheating"
        }

        # 6. Solar Rooftop Generation (Average 4.0 peak sun hours/day * 30 days = 120 kWh/month per kWp)
        solar_monthly_gen_kwh = solar_pv_kwp * 120.0
        kwh_savings_components["solar_generation"] = {
            "name": f"Rooftop Solar PV ({solar_pv_kwp} kWp)",
            "kwh_saved": round(solar_monthly_gen_kwh, 1),
            "description": f"On-site clean solar energy offset (120 kWh/kWp/month)"
        }

        total_kwh_saved = sum(item["kwh_saved"] for item in kwh_savings_components.values())
        # Cap realistic savings at 65% of total consumption to avoid impossible numbers
        total_kwh_saved = min(total_kwh_saved, current_monthly_kwh * 0.65)

        projected_monthly_kwh = max(100.0, current_monthly_kwh - total_kwh_saved)
        percentage_reduction = round((total_kwh_saved / current_monthly_kwh) * 100, 1)

        # Financial Calculations
        current_monthly_bill = self.calculate_bill(current_monthly_kwh)
        projected_monthly_bill = self.calculate_bill(projected_monthly_kwh)
        monthly_cost_saved = round(current_monthly_bill - projected_monthly_bill, 2)
        annual_cost_saved = round(monthly_cost_saved * 12, 2)

        # Carbon Calculations
        current_co2_kg = self.calculate_carbon_kg(current_monthly_kwh)
        projected_co2_kg = self.calculate_carbon_kg(projected_monthly_kwh)
        monthly_co2_saved_kg = round(current_co2_kg - projected_co2_kg, 2)
        annual_co2_saved_tonnes = round((monthly_co2_saved_kg * 12) / 1000.0, 2)

        # Estimated Capex for payback
        # LED retrofit cost: ₹350 per fixture (~200 fixtures total) * pct
        # ESP32 node cost: ₹1,200 per unit (~12 units) * pct
        # Solar PV: ₹45,000 per kWp
        # Geyser timers: ₹8,000 total
        capex_inr = (
            (led_retrofit_pct / 100.0 * 200 * 350) +
            (fan_eco_regulation_pct / 100.0 * 12 * 1200) +
            (solar_pv_kwp * 45000) +
            (8000 if geyser_timer_enabled else 0)
        )
        payback_months = round(capex_inr / max(1.0, monthly_cost_saved), 1) if monthly_cost_saved > 0 else 0

        # Block-wise estimated breakdown
        block_breakdown = {}
        for blk, info in Config.HOSTEL_BLOCKS.items():
            cap_share = info["capacity"] / 840.0 # total campus hostel capacity is 840
            block_breakdown[blk] = {
                "name": info["name"],
                "base_kwh": round(current_monthly_kwh * cap_share, 1),
                "projected_kwh": round(projected_monthly_kwh * cap_share, 1),
                "saved_kwh": round(total_kwh_saved * cap_share, 1),
                "saved_cost_inr": round(monthly_cost_saved * cap_share, 2)
            }

        return {
            "baseline": {
                "monthly_kwh": current_monthly_kwh,
                "monthly_bill_inr": current_monthly_bill,
                "monthly_co2_kg": current_co2_kg
            },
            "projected": {
                "monthly_kwh": round(projected_monthly_kwh, 1),
                "monthly_bill_inr": projected_monthly_bill,
                "monthly_co2_kg": projected_co2_kg
            },
            "savings": {
                "monthly_kwh": round(total_kwh_saved, 1),
                "percentage_reduction": percentage_reduction,
                "monthly_cost_inr": monthly_cost_saved,
                "annual_cost_inr": annual_cost_saved,
                "monthly_co2_kg": monthly_co2_saved_kg,
                "annual_co2_tonnes": annual_co2_saved_tonnes,
                "estimated_capex_inr": round(capex_inr, 2),
                "payback_months": payback_months
            },
            "components": kwh_savings_components,
            "block_breakdown": block_breakdown,
            "disclaimer": "Simulated estimates based on engineering thermal benchmarks and campus energy audits."
        }
