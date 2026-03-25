"""Static calculators used before the LLM/RAG pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


KWH_PER_SMC_GAS = 10.69
DEFAULT_BOILER_EFFICIENCY = 0.90
DEFAULT_HEAT_PUMP_COP = 3.20


def _is_italian(language: str | None) -> bool:
    print(f"Checking if language '{language}' is Italian")
    if language is None:
        print("Language is None, treating it as non-Italian")
        return False
    normalized = language.strip().lower()
    is_italian = normalized in {"italiano", "italian", "it", "it-it"}
    print(f"Normalized language is '{normalized}', Italian match: {is_italian}")
    return is_italian


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().replace(",", ".")
        return float(normalized)
    raise ValueError(f"Unsupported numeric value: {value!r}")


def _extract_json_object(raw_response: str) -> dict[str, Any]:
    print(f"Parsing LLM extraction payload: {raw_response}")
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(cleaned[start : end + 1])


@dataclass
class SavingsInputs:
    gas_consumption_smc: float | None = None
    gas_price_per_smc: float | None = None
    electricity_price_per_kwh: float | None = None
    boiler_efficiency: float = DEFAULT_BOILER_EFFICIENCY
    heat_pump_cop: float = DEFAULT_HEAT_PUMP_COP
    installation_cost: float | None = None


def extract_savings_intent_and_inputs(raw_response: str) -> tuple[bool, SavingsInputs]:
    payload = _extract_json_object(raw_response)
    should_calculate = bool(payload.get("should_calculate", False))
    print(f"LLM should_calculate flag: {should_calculate}")

    inputs = SavingsInputs(
        gas_consumption_smc=_coerce_float(payload.get("gas_consumption_smc")),
        gas_price_per_smc=_coerce_float(payload.get("gas_price_per_smc")),
        electricity_price_per_kwh=_coerce_float(payload.get("electricity_price_per_kwh")),
        installation_cost=_coerce_float(payload.get("installation_cost")),
    )

    boiler_efficiency = _coerce_float(payload.get("boiler_efficiency"))
    if boiler_efficiency is not None:
        inputs.boiler_efficiency = boiler_efficiency

    heat_pump_cop = _coerce_float(payload.get("heat_pump_cop"))
    if heat_pump_cop is not None:
        inputs.heat_pump_cop = heat_pump_cop

    print(f"Structured inputs from LLM: {inputs}")
    return should_calculate, inputs


def _format_currency(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_years(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def build_missing_inputs_message(language: str, inputs: SavingsInputs) -> str:
    print(f"Building missing-inputs message for language '{language}'")
    if _is_italian(language):
        missing = []
        if inputs.gas_consumption_smc is None:
            missing.append("consumo annuo gas in Smc")
        if inputs.gas_price_per_smc is None:
            missing.append("prezzo gas in euro/Smc")
        if inputs.electricity_price_per_kwh is None:
            missing.append("prezzo energia elettrica in euro/kWh")
        print(f"Missing required inputs: {missing}")
        requested = ", ".join(missing)
        return (
            "Per calcolare il risparmio economico della sostituzione gas -> HVAC "
            f"mi servono ancora: {requested}. "
            "Opzionali: rendimento caldaia %, COP pompa di calore e costo impianto."
        )

    missing = []
    if inputs.gas_consumption_smc is None:
        missing.append("annual gas consumption in Smc")
    if inputs.gas_price_per_smc is None:
        missing.append("gas price in euro/Smc")
    if inputs.electricity_price_per_kwh is None:
        missing.append("electricity price in euro/kWh")
    print(f"Missing required inputs: {missing}")
    requested = ", ".join(missing)
    return (
        "To calculate the economic savings for a gas -> HVAC replacement I still need: "
        f"{requested}. Optional: boiler efficiency %, heat pump COP, and installation cost."
    )


def calculate_gas_to_hvac_savings(language: str, inputs: SavingsInputs) -> str:
    print(f"Calculating gas-to-HVAC savings for language '{language}' with inputs: {inputs}")
    missing_required = (
        inputs.gas_consumption_smc is None
        or inputs.gas_price_per_smc is None
        or inputs.electricity_price_per_kwh is None
    )
    if missing_required:
        print("Required inputs are missing, returning follow-up prompt")
        return build_missing_inputs_message(language, inputs)

    usable_heat_kwh = (
        inputs.gas_consumption_smc * KWH_PER_SMC_GAS * inputs.boiler_efficiency
    )
    hvac_electricity_kwh = usable_heat_kwh / inputs.heat_pump_cop
    annual_gas_cost = inputs.gas_consumption_smc * inputs.gas_price_per_smc
    annual_hvac_cost = hvac_electricity_kwh * inputs.electricity_price_per_kwh
    annual_savings = annual_gas_cost - annual_hvac_cost
    print(
        "Calculated annual values:"
        f" usable_heat_kwh={usable_heat_kwh},"
        f" hvac_electricity_kwh={hvac_electricity_kwh},"
        f" annual_gas_cost={annual_gas_cost},"
        f" annual_hvac_cost={annual_hvac_cost},"
        f" annual_savings={annual_savings}"
    )

    payback_years = None
    if inputs.installation_cost and annual_savings > 0:
        payback_years = inputs.installation_cost / annual_savings
        print(f"Computed simple payback: {payback_years} years")
    elif inputs.installation_cost is not None:
        print("Installation cost provided, but annual savings are not positive")

    if _is_italian(language):
        print("Formatting response in Italian")
        lines = [
            "Stima del risparmio economico annuo gas -> HVAC:",
            f"- costo annuo attuale gas: {_format_currency(annual_gas_cost)} euro",
            f"- costo annuo stimato HVAC: {_format_currency(annual_hvac_cost)} euro",
            f"- risparmio annuo stimato: {_format_currency(annual_savings)} euro",
            (
                "- ipotesi usate: "
                f"{inputs.gas_consumption_smc:.0f} Smc/anno, "
                f"gas {inputs.gas_price_per_smc:.2f} euro/Smc, "
                f"elettricita {inputs.electricity_price_per_kwh:.2f} euro/kWh, "
                f"rendimento caldaia {inputs.boiler_efficiency * 100:.0f}%, "
                f"COP {inputs.heat_pump_cop:.2f}"
            ),
        ]
        if payback_years is not None:
            lines.append(f"- tempo di ritorno semplice: {_format_years(payback_years)} anni")
        elif inputs.installation_cost is not None and annual_savings <= 0:
            lines.append("- con queste ipotesi non emerge un risparmio annuo positivo.")
        print("Static savings response assembled in Italian")
        return "\n".join(lines)

    print("Formatting response in English")
    lines = [
        "Estimate of annual gas -> HVAC economic savings:",
        f"- current annual gas cost: {_format_currency(annual_gas_cost)} euro",
        f"- estimated annual HVAC cost: {_format_currency(annual_hvac_cost)} euro",
        f"- estimated annual savings: {_format_currency(annual_savings)} euro",
        (
            "- assumptions: "
            f"{inputs.gas_consumption_smc:.0f} Smc/year, "
            f"gas {inputs.gas_price_per_smc:.2f} euro/Smc, "
            f"electricity {inputs.electricity_price_per_kwh:.2f} euro/kWh, "
            f"boiler efficiency {inputs.boiler_efficiency * 100:.0f}%, "
            f"COP {inputs.heat_pump_cop:.2f}"
        ),
    ]
    if payback_years is not None:
        lines.append(f"- simple payback: {_format_years(payback_years)} years")
    elif inputs.installation_cost is not None and annual_savings <= 0:
        lines.append("- with these assumptions there is no positive annual saving.")
    print("Static savings response assembled in English")
    return "\n".join(lines)
