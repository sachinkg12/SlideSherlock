#!/usr/bin/env python3
"""
SlideSherlock CLI: quality presets and doctor checks.
Usage: slidesherlock doctor | slidesherlock preset [draft|standard|pro]
       python scripts/slidesherlock_cli.py doctor
       python scripts/slidesherlock_cli.py preset standard
       make doctor  # same as slidesherlock doctor
"""
from __future__ import annotations

import argparse
import os
import sys

# Add repo root and packages/core to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, "packages", "core"))


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run doctor checks."""
    from doctor import run_doctor, print_doctor_report

    report = run_doctor()
    print_doctor_report(report)
    return 0 if report.get("all_required_ok", False) else 1


def cmd_preset(args: argparse.Namespace) -> int:
    """Show or apply quality preset."""
    from presets import apply_preset, get_preset_env_vars, VALID_PRESETS

    preset = (args.preset or "").strip().lower()
    if not preset:
        print("Quality presets: draft | standard | pro")
        print("")
        print("  draft:    no vision, no bgm, cut transitions")
        print("  standard: notes overlay + crossfade + subtitles")
        print("  pro:      vision+merge + timeline actions + bgm ducking + loudness normalize")
        print("")
        print("Usage: slidesherlock preset <preset>")
        print("       SLIDESHERLOCK_PRESET=standard make worker")
        return 0
    if preset not in VALID_PRESETS:
        print(f"Unknown preset: {preset}. Valid: {', '.join(VALID_PRESETS)}", file=sys.stderr)
        return 1
    if args.export:
        for k, v in get_preset_env_vars(preset).items():
            print(f"export {k}={v!r}")
        return 0
    apply_preset(preset)
    os.environ["SLIDESHERLOCK_PRESET"] = preset
    print(f"Applied preset: {preset}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="slidesherlock",
        description="SlideSherlock CLI: quality presets and doctor checks",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # doctor
    doctor_parser = subparsers.add_parser("doctor", help="Check dependencies (LibreOffice, FFmpeg, Poppler, Tesseract)")
    doctor_parser.set_defaults(func=cmd_doctor)

    # preset
    preset_parser = subparsers.add_parser("preset", help="Show or apply quality preset (draft|standard|pro)")
    preset_parser.add_argument("preset", nargs="?", help="Preset name")
    preset_parser.add_argument("--export", "-e", action="store_true", help="Print export lines instead of applying")
    preset_parser.set_defaults(func=cmd_preset)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
