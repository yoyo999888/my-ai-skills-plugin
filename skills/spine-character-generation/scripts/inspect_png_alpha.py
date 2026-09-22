#!/usr/bin/env python3
"""Read-only PNG decoding/alpha inventory. Requires Pillow; makes no edits."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def inspect(path, near_opaque_min):
    result = {"path": str(path), "issues": []}
    try:
        payload = path.read_bytes()
        result["sha256"] = hashlib.sha256(payload).hexdigest()
        with Image.open(path) as im:
            im.load()
            if im.format != "PNG":
                raise ValueError("Input suffix is .png but decoded format is not PNG")
            result.update({"source_mode": im.mode, "size": list(im.size)})
            result["source_has_alpha"] = "A" in im.getbands() or "transparency" in im.info
            # Palette transparency is valid alpha; RGB -> RGBA is fully opaque.
            hist = im.convert("RGBA").getchannel("A").histogram()
        present = [i for i, count in enumerate(hist) if count]
        result.update({
            "decoded": True,
            "alpha_min": min(present),
            "alpha_max": max(present),
            "pixel_count": sum(hist),
            "clear_pixels": hist[0],
            "partial_alpha_pixels": sum(hist[1:255]),
            "fully_opaque_pixels": hist[255],
            "near_opaque_pixels": sum(hist[near_opaque_min:255]),
            "has_transparency": sum(hist[:255]) > 0,
            "near_opaque_without_fully_opaque": sum(hist[near_opaque_min:255]) > 0 and hist[255] == 0,
        })
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        result.update({"decoded": False, "error": str(exc)})
        result["issues"].append("decode_failed")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="PNG files or directories (recursive)")
    parser.add_argument("--report", type=Path, help="Write a .json report; image inputs are never modified")
    parser.add_argument("--require-transparency", action="store_true", help="Require at least one pixel with alpha <255")
    parser.add_argument("--require-clear-pixels", action="store_true", help="Require at least one alpha=0 pixel; does not certify a clean perimeter")
    parser.add_argument("--require-opaque-pixels", action="store_true", help="Require alpha=255 pixels only when intended by material design")
    parser.add_argument("--near-opaque-min", type=int, default=248, help="Diagnostic range [value,254]; no normalization is performed")
    args = parser.parse_args()
    if not 1 <= args.near_opaque_min <= 254:
        parser.error("--near-opaque-min must be between 1 and 254")
    files = set()
    for item in args.inputs:
        if item.is_dir():
            files.update(p.resolve() for p in item.rglob("*") if p.is_file() and p.suffix.lower() == ".png")
        elif item.is_file() and item.suffix.lower() == ".png":
            files.add(item.resolve())
        else:
            parser.error("Not a PNG file or directory: " + str(item))
    if not files:
        parser.error("No PNG files found")
    if args.report and (args.report.suffix.lower() != ".json" or args.report.resolve() in files):
        parser.error("--report must name a .json file separate from inputs")
    records = []
    for path in sorted(files):
        row = inspect(path, args.near_opaque_min)
        if row["decoded"]:
            if args.require_transparency and not row["has_transparency"]:
                row["issues"].append("transparency_required")
            if args.require_clear_pixels and not row["clear_pixels"]:
                row["issues"].append("clear_pixels_required")
            if args.require_opaque_pixels and not row["fully_opaque_pixels"]:
                row["issues"].append("opaque_pixels_required")
        records.append(row)
    report = {
        "schema": "png-alpha-inspection-v1",
        "policy": {"require_transparency": args.require_transparency, "require_clear_pixels": args.require_clear_pixels, "require_opaque_pixels": args.require_opaque_pixels, "near_opaque_min": args.near_opaque_min},
        "scope": "Decoded alpha statistics only; not seam, style, animation, or legal acceptance. No input edits.",
        "files": records,
        "summary": {"files": len(records), "decoded": sum(r["decoded"] for r in records), "flagged": sum(bool(r["issues"]) for r in records)},
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({**report["summary"], "report": str(args.report)}, ensure_ascii=False))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["summary"]["flagged"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
