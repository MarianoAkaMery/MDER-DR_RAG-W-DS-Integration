"""Static calculators used before the LLM/RAG pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass


KWH_PER_SMC_GAS = 10.69
DEFAULT_BOILER_EFFICIENCY = 0.90
DEFAULT_HEAT_PUMP_COP = 3.20


def _is_italian(language: str | None) -> bool:
    if language is None:
        return False
    normalized = language.strip().lower()
    return normalized in {"italiano", "italian", "it", "it-it"}


def _parse_number(raw_value: str) -> float:
    normalized = raw_value.strip().replace(".", "").replace(",", ".")
    return float(normalized)


def _extract_number(pattern: str, message: str) -> float | None:
    match = re.search(pattern, message, flags=re.IGNORECASE)
    if not match:
        return None
    return _parse_number(match.group(1))


@dataclass
class SavingsInputs:
    gas_consumption_smc: float | None = None
    gas_price_per_smc: float | None = None
    electricity_price_per_kwh: float | None = None
    boiler_efficiency: float = DEFAULT_BOILER_EFFICIENCY
    heat_pump_cop: float = DEFAULT_HEAT_PUMP_COP
    installation_cost: float | None = None


def should_calculate_gas_to_hvac_savings(message: str) -> bool:
    lowered = message.lower()
    has_calc_intent = any(
        token in lowered
        for token in ("calcola", "calcolare", "calcolo", "stimare", "stima")
    )
    has_savings_intent = any(
        token in lowered
        for token in ("risparmio", "risparmio economico", "spesa", "costo", "bolletta")
    )
    has_gas = "gas" in lowered
    has_hvac = any(
        token in lowered
        for token in ("hvac", "pompa di calore", "heat pump", "climatizzazione")
    )
    return has_calc_intent and has_savings_intent and has_gas and has_hvac


def extract_savings_inputs(message: str) -> SavingsInputs:
    inputs = SavingsInputs()
    inputs.gas_consumption_smc = _extract_number(
        r"(\d+(?:[.,]\d+)?)\s*(?:smc|sm3|m3|mc)\b", message
    )
    inputs.gas_price_per_smc = _extract_number(
        r"(?:prezzo\s+gas|gas\s*price|costo\s+gas)[^\d]*(\d+(?:[.,]\d+)?)\s*(?:€|euro)?\s*/?\s*(?:smc|sm3|m3|mc)",
        message,
    )
    inputs.electricity_price_per_kwh = _extract_number(
        r"(?:prezzo\s+(?:elettricita|energia elettrica)|electricity\s*price|costo\s+(?:luce|elettricita|energia elettrica))[^\d]*(\d+(?:[.,]\d+)?)\s*(?:€|euro)?\s*/?\s*kwh",
        message,
    )

    boiler_efficiency = _extract_number(
        r"(?:rendimento\s+(?:caldaia|impianto\s+gas)|efficienza\s+(?:caldaia|impianto\s+gas))[^\d]*(\d+(?:[.,]\d+)?)\s*%",
        message,
    )
    if boiler_efficiency is not None:
        inputs.boiler_efficiency = boiler_efficiency / 100

    heat_pump_cop = _extract_number(
        r"\bcop\b[^\d]*(\d+(?:[.,]\d+)?)", message
    )
    if heat_pump_cop is not None:
        inputs.heat_pump_cop = heat_pump_cop

    inputs.installation_cost = _extract_number(
        r"(?:costo\s+(?:impianto|installazione|hvac)|investimento)[^\d]*(\d+(?:[.,]\d+)?)\s*(?:€|euro)",
        message,
    )
    return inputs


def _format_currency(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_years(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def build_missing_inputs_message(language: str, inputs: SavingsInputs) -> str:
    missing = []
    if inputs.gas_consumption_smc is None:
        missing.append("consumo annuo gas in Smc")
    if inputs.gas_price_per_smc is None:
        missing.append("prezzo gas in euro/Smc")
    if inputs.electricity_price_per_kwh is None:
        missing.append("prezzo energia elettrica in euro/kWh")

    if _is_italian(language):
        requested = ", ".join(missing)
        return (
            "Per calcolare il risparmio economico della sostituzione gas -> HVAC "
            f"mi servono ancora: {requested}. "
            "Opzionali: rendimento caldaia %, COP pompa di calore e costo impianto."
        )

    requested = ", ".join(missing)
    return (
        "To calculate the economic savings for a gas -> HVAC replacement I still need: "
        f"{requested}. Optional: boiler efficiency %, heat pump COP, and installation cost."
    )


def calculate_gas_to_hvac_savings(
    language: str, inputs: SavingsInputs
) -> str:
    missing_required = (
        inputs.gas_consumption_smc is None
        or inputs.gas_price_per_smc is None
        or inputs.electricity_price_per_kwh is None
    )
    if missing_required:
        return build_missing_inputs_message(language, inputs)

    usable_heat_kwh = (
        inputs.gas_consumption_smc * KWH_PER_SMC_GAS * inputs.boiler_efficiency
    )
    hvac_electricity_kwh = usable_heat_kwh / inputs.heat_pump_cop
    annual_gas_cost = inputs.gas_consumption_smc * inputs.gas_price_per_smc
    annual_hvac_cost = hvac_electricity_kwh * inputs.electricity_price_per_kwh
    annual_savings = annual_gas_cost - annual_hvac_cost

    payback_years = None
    if inputs.installation_cost and annual_savings > 0:
        payback_years = inputs.installation_cost / annual_savings

    if _is_italian(language):
        lines = [
            "Stima statica del risparmio economico annuo gas -> HVAC:",
            f"- costo annuo attuale gas: { _format_currency(annual_gas_cost) } euro",
            f"- costo annuo stimato HVAC: { _format_currency(annual_hvac_cost) } euro",
            f"- risparmio annuo stimato: { _format_currency(annual_savings) } euro",
            f"- ipotesi usate: {inputs.gas_consumption_smc:.0f} Smc/anno, gas {inputs.gas_price_per_smc:.2f} euro/Smc, elettricita {inputs.electricity_price_per_kwh:.2f} euro/kWh, rendimento caldaia {inputs.boiler_efficiency * 100:.0f}%, COP {inputs.heat_pump_cop:.2f}",
        ]
        if payback_years is not None:
            lines.append(
                f"- tempo di ritorno semplice: {_format_years(payback_years)} anni"
            )
        elif inputs.installation_cost is not None and annual_savings <= 0:
            lines.append("- con queste ipotesi non emerge un risparmio annuo positivo.")
        return "\n".join(lines)

    lines = [
        "Static estimate of annual gas -> HVAC economic savings:",
        f"- current annual gas cost: {_format_currency(annual_gas_cost)} euro",
        f"- estimated annual HVAC cost: {_format_currency(annual_hvac_cost)} euro",
        f"- estimated annual savings: {_format_currency(annual_savings)} euro",
        f"- assumptions: {inputs.gas_consumption_smc:.0f} Smc/year, gas {inputs.gas_price_per_smc:.2f} euro/Smc, electricity {inputs.electricity_price_per_kwh:.2f} euro/kWh, boiler efficiency {inputs.boiler_efficiency * 100:.0f}%, COP {inputs.heat_pump_cop:.2f}",
    ]
    if payback_years is not None:
        lines.append(f"- simple payback: {_format_years(payback_years)} years")
    elif inputs.installation_cost is not None and annual_savings <= 0:
        lines.append("- with these assumptions there is no positive annual saving.")
    return "\n".join(lines)
