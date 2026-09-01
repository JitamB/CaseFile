"""Measure the S1 materiality gate's real false-alarm rate — ADA-2, docs/ada-integration-plan.md.

`stats/materiality.py::assess()`'s own docstring already states one measurement: four
regions, the trailing twelve periods, 48 region-periods, of the real generated
corpus — exactly three material movements, the three sealed scenarios. That is one
seed's worth of one specific narrative, not evidence about the gate's own behaviour
in general, and every one of those region-periods was hand-authored to be either
clearly material or clearly not — none of them is a coin flip.

This script measures the gate the way ADA's own tools/calibrate_anomalies.py measures
its anomaly band: simulate many *stable* series — a seasonal shape plus noise, nothing
worth flagging in any period, least of all the last one — run the real `assess()` at
this project's actual contract thresholds, and report how often it fires anyway. No
generator, no warehouse, no scenario narrative: `assess()` is a pure function of a
numeric series and a contract's four thresholds, and that is exactly what gets
simulated here, the same way ADA's own calibration bypasses its whole app and works
directly against `fit_trendline`.

Each contract's simulated level is `absolute ÷ relative` — the series magnitude at
which the gate's own two business thresholds coincide, derived from the contract
rather than guessed, so no contract is trivially always-blocked or always-cleared by
the absolute condition alone.

Unlike ADA's script, this one does not solve for a threshold — §23's four conditions
are fixed by contract, not tuned to hit a target rate. It only measures what the
existing thresholds actually do, so the number in `tests/test_materiality.py`'s own
bound is read off a real run of this script, not invented first.

    python tools/calibrate_materiality.py
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from casefile.contract import load  # noqa: E402
from casefile.models import Materiality  # noqa: E402
from casefile.stats.materiality import assess  # noqa: E402

FALSE_ALARM_TARGET = 0.05
#: §22's real corpus depth, and verify.py's own "three seasonal cycles" comment —
#: the length materiality.assess() actually sees in production, not a round number.
HISTORY_MONTHS = 36
SEASONAL_PERIOD = 12
NOISE_SD = 0.04
SEASONAL_AMPLITUDE = 0.06
TRIALS = 3_000
SEED = 2024
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"


def _stable_series(rng: random.Random, level: float) -> list[float]:
    """A repeating seasonal shape plus independent monthly noise — nothing
    worth flagging anywhere, including the last period. STL should recover
    the fixed seasonal shape almost exactly, leaving noise as the residual;
    the raw month-over-month change (what `assess()` computes `delta` from)
    still swings with the season, which is the real case this gate exists to
    tell apart from an actual movement.
    """
    return [
        level
        * (1.0 + SEASONAL_AMPLITUDE * math.sin(2 * math.pi * month / SEASONAL_PERIOD))
        * (1.0 + rng.gauss(0.0, NOISE_SD))
        for month in range(HISTORY_MONTHS)
    ]


def false_alarm_rate(materiality: Materiality, trials: int, rng: random.Random) -> float:
    level = materiality.absolute / materiality.relative if materiality.relative else materiality.absolute
    fires = sum(
        assess(
            _stable_series(rng, level),
            period=SEASONAL_PERIOD,
            relative=materiality.relative,
            absolute=materiality.absolute,
            z_threshold=materiality.z_threshold,
            min_persistence=materiality.min_persistence,
        ).passed
        for _ in range(trials)
    )
    return fires / trials


def main() -> None:
    rng = random.Random(SEED)
    print(f"Target false-alarm rate: {FALSE_ALARM_TARGET:.0%}  (n={TRIALS} per contract)\n")
    for path in sorted(CONTRACTS_DIR.glob("*.yaml")):
        contract = load(path)
        rate = false_alarm_rate(contract.materiality, TRIALS, rng)
        flag = "" if rate <= FALSE_ALARM_TARGET else "  <-- above target"
        print(f"{contract.id:<24} {rate:6.2%}{flag}")


if __name__ == "__main__":
    main()
