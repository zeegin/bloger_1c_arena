#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class Stat:
    total: int = 0
    satisfied: int = 0
    tolerating: int = 0
    frustrated: int = 0
    errors: int = 0
    total_ms: float = 0.0
    min_ms: float | None = None
    max_ms: float | None = None

    def apdex(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.satisfied + 0.5 * self.tolerating) / self.total

    def avg_ms(self) -> float:
        if self.total == 0:
            return 0.0
        return self.total_ms / self.total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate Apdex per action from metrics JSONL log."
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("/data/metrics/actions.log"),
        help="Path to JSONL log or directory with logs (default: /data/metrics/actions.log)",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=500.0,
        help="Satisfied threshold in ms (default: 500)",
    )
    parser.add_argument(
        "--factor",
        type=float,
        default=4.0,
        help="Tolerating multiplier relative to target (default: 4x)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("apdex_report.md"),
        help="Where to write Markdown report (default: ./apdex_report.md)",
    )
    return parser.parse_args()


def iter_logs(path: Path):
    if path.is_file():
        yield path
    elif path.is_dir():
        for entry in sorted(path.glob("*.log*")):
            if entry.is_file():
                yield entry
    else:
        raise FileNotFoundError(f"No such log file or directory: {path}")


def collect_stats(log_path: Path, target_ms: float, tolerating_factor: float) -> dict[str, Stat]:
    tolerance_ms = target_ms * tolerating_factor
    stats: dict[str, Stat] = defaultdict(Stat)
    found_files = False
    try:
        for file in iter_logs(log_path):
            found_files = True
            with file.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    action = payload.get("action")
                    duration = float(payload.get("duration_ms", 0))
                    success = bool(payload.get("success", False))
                    if not action:
                        continue
                    key = aggregate_key(action, payload)
                    stat = stats[key]
                    stat.total += 1
                    stat.total_ms += duration
                    stat.min_ms = duration if stat.min_ms is None else min(stat.min_ms, duration)
                    stat.max_ms = duration if stat.max_ms is None else max(stat.max_ms, duration)
                    if not success:
                        stat.errors += 1
                    if duration <= target_ms:
                        stat.satisfied += 1
                    elif duration <= tolerance_ms:
                        stat.tolerating += 1
                    else:
                        stat.frustrated += 1
    except FileNotFoundError:
        print(f"[WARN] Log path '{log_path}' not found, skipping.")
        return {}
    if not found_files:
        print(f"[WARN] No log files discovered under '{log_path}'.")
    return stats


def aggregate_key(action: str, payload: Dict[str, Any]) -> str:
    cache_state = payload.get("media_cache")

    def with_cache(base: str) -> str:
        if cache_state in {"hit", "halfhit", "miss"}:
            return f"{base} [cache={cache_state}]"
        return base

    if action.startswith("callback:vote"):
        return with_cache("callback:vote")
    if action.startswith("callback:dmvote"):
        return with_cache("callback:dmvote")
    return action


def render_markdown(stats: dict[str, Stat], output: Path, target_ms: float, tolerating_factor: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# Apdex report",
        "",
        f"- Satisfied threshold: `{target_ms} ms`",
        f"- Tolerating threshold: `{target_ms * tolerating_factor} ms` (factor {tolerating_factor}×)",
        "",
        "| Action | Calls | Apdex | Grade | Avg ms | Min ms | Max ms | Errors | Sat | Tol | Frus |",
        "| --- | ---: | ---: | :-: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for action in sorted(stats):
        stat = stats[action]
        apdex_value = stat.apdex()
        lines.append(
            f"| `{action}` | {stat.total} | {apdex_value:.3f} | {letter_grade(apdex_value)} | {stat.avg_ms():.1f} | "
            f"{(stat.min_ms or 0):.1f} | {(stat.max_ms or 0):.1f} | {stat.errors} | "
            f"{stat.satisfied} | {stat.tolerating} | {stat.frustrated} |"
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def letter_grade(value: float) -> str:
    if value >= 0.94:
        return "A"
    if value >= 0.85:
        return "B"
    if value >= 0.70:
        return "C"
    if value >= 0.50:
        return "D"
    return "E"


def main() -> None:
    args = parse_args()
    stats = collect_stats(args.log, args.target, args.factor)
    if not stats:
        print("No actions found. Did you point to the correct log?")
        return
    render_markdown(stats, args.output, args.target, args.factor)
    print(f"Wrote report to {args.output}")


if __name__ == "__main__":
    main()
