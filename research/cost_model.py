"""Reproducible planning model; assumptions are not measured usage or invoices.

Run: python3 research/cost_model.py
Public price references and billing caveats: research/03-economics.md
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Assumptions:
    price: float = 6.0
    answers_per_hour: float = 20.0
    input_tokens: int = 6000
    output_tokens: int = 250
    cheap_input_per_million: float = 0.10
    cheap_output_per_million: float = 0.40
    premium_input_per_million: float = 3.0
    premium_output_per_million: float = 15.0
    premium_fraction: float = 0.10
    summary_per_hour: float = 0.02
    retrieval_search_per_hour: float = 0.01
    api_reserve: float = 0.15
    monthly_hosting_support: float = 1.0
    payment_fraction: float = 0.03
    payment_fixed: float = 0.30


@dataclass(frozen=True)
class Configuration:
    name: str
    stt_per_billable_hour: float
    billable_stream_multiplier: float = 1.0
    capture_per_cloud_hour: float = 0.0
    cloud_stt_fraction: float = 1.0


def answer_cost(a: Assumptions) -> float:
    cheap = (a.input_tokens * a.cheap_input_per_million
             + a.output_tokens * a.cheap_output_per_million) / 1_000_000
    premium = (a.input_tokens * a.premium_input_per_million
               + a.output_tokens * a.premium_output_per_million) / 1_000_000
    return cheap * (1 - a.premium_fraction) + premium * a.premium_fraction


def hourly_cost(config: Configuration, a: Assumptions) -> float:
    stt = (config.cloud_stt_fraction * config.billable_stream_multiplier
           * config.stt_per_billable_hour)
    capture = config.cloud_stt_fraction * config.capture_per_cloud_hour
    inference = a.answers_per_hour * answer_cost(a)
    return (stt + capture + inference + a.summary_per_hour
            + a.retrieval_search_per_hour) * (1 + a.api_reserve)


def monthly_cost(hours: float, config: Configuration, a: Assumptions) -> float:
    return (hours * hourly_cost(config, a) + a.monthly_hosting_support
            + a.price * a.payment_fraction + a.payment_fixed)


def max_hours_at_margin(config: Configuration, a: Assumptions,
                        target_margin: float = 0.60) -> float:
    allowance = (a.price * (1 - target_margin) - a.monthly_hosting_support
                 - a.price * a.payment_fraction - a.payment_fixed)
    rate = hourly_cost(config, a)
    return max(0.0, allowance / rate) if rate else float("inf")


def main() -> None:
    a = Assumptions()
    configs = [
        Configuration("Local STT + cloud answers", 0, cloud_stt_fraction=0),
        Configuration("Native + cloud STT x1", 0.15),
        Configuration("Native + cloud STT x2", 0.15, 2),
        Configuration("Native + Nova3 promo x1", 0.0048 * 60),
        Configuration("Native + Nova3 regular x1", 0.0077 * 60),
        Configuration("Recall capture + built-in STT", 0.15,
                      capture_per_cloud_hour=0.50),
    ]
    print("USD; modeled estimates, not measured invoices. Price: $6/month.")
    print(f"Weighted answer cost: ${answer_cost(a):.6f}")
    print(f"{'Configuration':35} {'Hours':>6} {'Cost':>8} {'Contrib':>8} {'Margin':>8}")
    for config in configs:
        for hours in (5, 10, 20, 40, 80):
            cost = monthly_cost(hours, config, a)
            contribution = a.price - cost
            print(f"{config.name:35} {hours:6} {cost:8.2f} "
                  f"{contribution:8.2f} {contribution / a.price:7.1%}")
        print(f"  Hours at 60% contribution target: {max_hours_at_margin(config, a):.2f}")


if __name__ == "__main__":
    main()
