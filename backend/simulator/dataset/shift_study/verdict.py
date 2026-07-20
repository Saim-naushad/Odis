"""Study-level verdict: primary/secondary/minor attribution and the next-
engineering-direction recommendation (spec sections 11-12).

The recommendation logic is fixed here, in code, before any study is run
— it is never adjusted to fit a particular result (spec section 7/11's
explicit instruction).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backend.simulator.dataset.shift_study.config import (
    INVALID_ROW_FRACTION_MATERIAL_THRESHOLD,
)
from backend.simulator.dataset.shift_study.interaction_analysis import (
    InteractionFindings,
    InteractionLikelihood,
)
from backend.simulator.dataset.shift_study.rankings import ShiftDamage, tier_rank

Recommendation = Literal["A", "B", "C", "D"]

_MAJORITY_MAJOR_OR_WORSE_COUNT = 3
"""If at least this many isolated shifts independently reach `major` or
`catastrophic`, failures are read as "broad and severe even for modest
isolated shifts" (recommendation D's own criterion)."""

RECOMMENDATION_DESCRIPTIONS: dict[Recommendation, str] = {
    "A": "Numerically harden existing features first — the invalid/null "
    "row-ratio behavior is materially important in at least one cohort.",
    "B": "Add load-conditioned and training-fitted healthy residual "
    "features — the high-load shift dominates without major numerical "
    "failures elsewhere.",
    "C": "Broaden training-distribution coverage first — no single "
    "isolated shift's failure mode is decisive enough on its own to "
    "justify a targeted feature or architecture change; see "
    "`recommendation_reasons` for this study's specific trigger.",
    "D": "Reconsider the current model/feature architecture — failures "
    "are broad and severe even for modest isolated shifts.",
}


def determine_recommendation(
    isolated_damages: dict[str, ShiftDamage], invalid_rows: dict[str, Any]
) -> tuple[Recommendation, list[str]]:
    reasons: list[str] = []

    cohort_fractions = {
        name: finding["unscoreable_fraction"]
        for name, finding in invalid_rows["by_cohort"].items()
    }
    max_fraction_cohort = max(
        cohort_fractions, key=lambda n: (cohort_fractions[n], n), default=None
    )
    if max_fraction_cohort is not None and (
        cohort_fractions[max_fraction_cohort] > INVALID_ROW_FRACTION_MATERIAL_THRESHOLD
    ):
        reasons.append(
            f"{max_fraction_cohort}'s invalid-row fraction "
            f"({cohort_fractions[max_fraction_cohort]:.2%}) exceeds the "
            f"materiality threshold ({INVALID_ROW_FRACTION_MATERIAL_THRESHOLD:.2%})"
        )
        return "A", reasons

    tiers = {name: damage.tier for name, damage in isolated_damages.items()}
    major_or_worse = sorted(
        name for name, tier in tiers.items() if tier_rank(tier) >= tier_rank("major")
    )
    if len(major_or_worse) >= _MAJORITY_MAJOR_OR_WORSE_COUNT:
        reasons.append(
            f"{len(major_or_worse)}/{len(tiers)} isolated shifts independently "
            f"reached major or catastrophic severity: {major_or_worse}"
        )
        return "D", reasons

    high_load_tier = tiers.get("high_load")
    other_tiers = {name: tier for name, tier in tiers.items() if name != "high_load"}
    if (
        high_load_tier is not None
        and tier_rank(high_load_tier) >= tier_rank("major")
        and all(tier_rank(tier) < tier_rank("major") for tier in other_tiers.values())
    ):
        reasons.append(
            "high_load is the only isolated shift reaching major/catastrophic "
            f"severity (tier={high_load_tier!r}); every other isolated shift "
            f"stayed below major: {other_tiers}"
        )
        return "B", reasons

    if tiers and all(tier == "moderate" for tier in tiers.values()):
        reasons.append(
            "every isolated shift classified as moderate — no single dominant "
            "failure mode; the model appears to mainly lack training-distribution "
            "exposure rather than have a structural flaw"
        )
        return "C", reasons

    reasons.append(
        "no single decisive pattern matched the A/B/D criteria; defaulting to "
        "broadening training-distribution coverage as the conservative next step"
    )
    return "C", reasons


@dataclass(frozen=True)
class StudyVerdict:
    primary_failure: str | None
    secondary_failure: str | None
    minor_contributors: list[str]
    interaction_effects_likely: InteractionLikelihood
    recommendation: Recommendation
    recommendation_description: str
    recommendation_reasons: list[str]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "primary_failure": self.primary_failure,
            "secondary_failure": self.secondary_failure,
            "minor_contributors": self.minor_contributors,
            "interaction_effects_likely": self.interaction_effects_likely,
            "recommendation": self.recommendation,
            "recommendation_description": self.recommendation_description,
            "recommendation_reasons": self.recommendation_reasons,
        }


def determine_study_verdict(
    isolated_damages: dict[str, ShiftDamage],
    interaction: InteractionFindings,
    invalid_rows: dict[str, Any],
) -> StudyVerdict:
    ranked = sorted(
        isolated_damages,
        key=lambda name: (
            -tier_rank(isolated_damages[name].tier),
            -isolated_damages[name].balanced_accuracy_drop,
            name,
        ),
    )

    primary = ranked[0] if ranked else None
    secondary = ranked[1] if len(ranked) > 1 else None
    if secondary is not None and tier_rank(
        isolated_damages[secondary].tier
    ) < tier_rank("moderate"):
        secondary = None
    minor_contributors = [
        name for name in ranked if name not in (primary, secondary)
    ]

    recommendation, reasons = determine_recommendation(isolated_damages, invalid_rows)

    return StudyVerdict(
        primary_failure=primary,
        secondary_failure=secondary,
        minor_contributors=minor_contributors,
        interaction_effects_likely=interaction.interaction_effects_likely,
        recommendation=recommendation,
        recommendation_description=RECOMMENDATION_DESCRIPTIONS[recommendation],
        recommendation_reasons=reasons,
    )
