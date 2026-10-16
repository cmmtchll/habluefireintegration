"""Export the curated dictionary or look up an explicitly namespaced code."""

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.bluefire.catalog import (  # noqa: E402
    NAMESPACES, PROFILES, describe_fault, export_catalog, lookup,
)


def render_markdown(catalog: dict) -> str:
    """Render every known mapping deterministically for the checked-in docs."""
    lines = [
        "# BlueFire vehicle code reference", "",
        "[Integration README](../README.md)", "",
        "Generated from the shared code dictionary. Do not edit tables by "
        "hand; update the dictionary and regenerate this file.", "",
        "```powershell",
        "python .\\scripts\\catalog_bluefire.py --markdown "
        "--output .\\docs\\code-reference.md",
        "```", "",
        f"Catalog version: **{catalog['catalog_version']}**. "
        f"{catalog['coverage']}", "",
        "Vehicle context: **2003-era Detroit Diesel, 500 HP, "
        "Allison B500**. Year, horsepower and transmission model do not "
        "identify the ECM/controller generation or calibration. Profiles "
        "below are reference-only and never selected automatically.", "",
        "J1939 SPNs, J1587 PIDs/SIDs, OBD mode/PIDs, Detroit flash codes "
        "and Allison main/subcodes are separate namespaces. A number alone "
        "is not enough to identify its meaning. Unknown codes retain their "
        "IDs and an explicit unmapped label; no meaning is guessed.", "",
        "Source-address and MID labels are conventional roles, not verified "
        "ECU identities. These are independently worded factual summaries, "
        "not a complete service manual or a repair/safety assessment.", "",
        "## J1939 decoded measurements", "",
        "Offsets are zero-based byte offsets; values are little-endian. "
        "Engineering value = raw * resolution + offset. Numeric raw values "
        "at or above 0xFB shifted to the most-significant byte become null; "
        "this rule must not be applied to enumerations.", "",
    ]

    def table(headers, rows):
        def escape(value):
            if value is None:
                return "-"
            return str(value).replace("|", "\\|").replace("\n", " ")

        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        lines.extend(
            "| " + " | ".join(escape(value) for value in row) + " |"
            for row in rows
        )
        lines.append("")

    table(
        ("PGN", "SPN", "Label", "Unit", "Byte", "Bytes", "Resolution",
         "Offset", "HA state class", "Description"),
        (
            (p["pgn"], p["spn"], p["name"], p["unit"], p["start"],
             p["length"], p["resolution"], p["offset"], p["state_class"],
             p["description"])
            for p in catalog["measurements"]
        ),
    )
    lines.extend([
        "Measurement provenance: " + catalog["references"]["signals"], "",
        "## J1708/J1587 decoded measurements", "",
        "These independent PID definitions are not J1939 layouts. The "
        "parameter value excludes its PID and any variable-parameter "
        "byte-count prefix. Engineering value = raw * resolution + offset, "
        "rounded to six decimals. All-ones values become null using the "
        "observed BlueFire unavailable convention; J1939's upper reserved "
        "ranges are not reused.", "",
        "Native units include mph, psi, degrees Fahrenheit and US gallons. "
        "Conversions use 1 mile = 1.609344 km and "
        "1 US gallon = 3.785411784 L. "
        "Other mapped PIDs below may have labels without a value decoder; "
        "they remain raw-only rather than borrowing a J1939 scale.", "",
    ])
    table(
        ("PID", "Label", "Value bytes", "Output unit", "Resolution",
         "Offset", "HA state class", "Description"),
        (
            (p["pid"], p["name"], p["length"], p["unit"], p["resolution"],
             p["offset"], p["state_class"], p["description"])
            for p in catalog["j1587_measurements"]
        ),
    )
    lines.extend([
        "J1587 provenance: " + catalog["references"]["j1587"], "",
        "## Standard code labels", "",
        "For J1587 PID lookups, units mean preferred display units only; "
        "an actual conversion is implemented only for the decoded subset "
        "above. Faults do not carry measurement units. OBD labels are "
        "mode-specific and do not imply an OBD value decoder.", "",
    ])
    for namespace in NAMESPACES:
        records = [
            p for p in catalog["codes"] if p["namespace"] == namespace
        ]
        if not records:
            continue
        lines.extend([f"### {namespace.upper()}", ""])
        if namespace == "fmi":
            lines.extend([
                "These FMI values apply to J1939. J1587 uses the "
                "separate four-bit table below.", "",
            ])
        table(
            ("Code / ID", "Label string", "Unit", "Description", "Reference"),
            (
                (p["code"], p["name"], p["unit"], p["description"],
                 p["reference"])
                for p in records
            ),
        )
    lines.extend(["## J1587 failure modes", ""])
    table(
        ("FMI", "Description"),
        sorted(catalog["j1587_failure_modes"].items()),
    )
    lines.extend([
        "## J1939 diagnostic lamp strings", "",
        "Lamp status and flash are separate two-bit fields, shared by the "
        "report rather than assigned to individual DTCs.", "",
    ])
    table(
        ("Code", "Status string", "Flash string"),
        (
            (code, label, catalog["j1939_lamp_flash"][code])
            for code, label in sorted(catalog["j1939_lamp_status"].items())
        ),
    )
    lines.extend([
        "Lamp provenance: " + catalog["references"]["j1939"], "",
        "## Manufacturer-scoped references", "",
        "Codes are matched only inside the specified profile/namespace. "
        "PID/SID equivalents are J1587 codes, not J1939 SPNs. "
        "No Allison selector-to-SPN or P-code translation is inferred.", "",
    ])
    for profile, details in catalog["profiles"].items():
        lines.extend([
            f"### {details['name']} (`{profile}`)", "",
            details["applicability"], "", details["coverage"], "",
        ])
        records = [
            p for p in catalog["manufacturer_codes"]
            if p["profile"] == profile
        ]
        table(
            ("Namespace", "Code", "Label / description",
             "J1587 equivalents (code / FMI)", "Reference"),
            (
                (p["namespace"], p["code"], p["name"],
                 ", ".join(
                     f"{kind} {code} / {fmi}"
                     for kind, pairs in (
                         ("PID", p["pid_fmi"]), ("SID", p["sid_fmi"])
                     ) for code, fmi in pairs
                 ) or "-", p["reference"])
                for p in records
            ),
        )
    lines.extend([
        "## Controller-scoped SID labels", "",
        "These require engine MID 128 and the explicit Detroit DDEC III/IV "
        "reference profile. Injector/cylinder/bank numbering must be checked "
        "against the actual engine manual.", "",
    ])
    table(
        ("Profile", "MID", "SID", "Label / description", "Reference"),
        (
            (p["profile"], p["source"], p["code"], p["name"], p["reference"])
            for p in catalog["scoped_sids"]
        ),
    )
    lines.extend([
        "## Diagnostic framing and output strings", "",
        "- J1939 DM1 is PGN 65226 (active); DM2 is PGN 65227 "
        "(previously active). Conversion method 0 is decoded. Method 1 is "
        "`unsupported_conversion` and has no inferred SPN.",
        "- J1939 decode statuses: `decoded`, `unavailable`, "
        "`unsupported_conversion`. All-zero DTC: `No active faults` or "
        "`No previously active faults`. All-FF DTC: "
        "`Diagnostics unavailable`, never healthy.",
        "- J1587 PID 194: each entry has code, flags/FMI and an optional "
        "occurrence byte. Bit 4 selects SID (otherwise PID); bit 5 clear "
        "adds 256; bit 6 means inactive; bit 7 includes occurrence count. "
        "Low four bits are FMI. Raw bytes and active/inactive status remain "
        "in the output.",
        "- J1587 empty diagnostic list: `No faults in this report`, not "
        "vehicle-wide health. Otherwise the summary gives active/inactive "
        "entry counts. Diagnostic lookup never auto-selects a profile.",
        "- Unknowns: `Unmapped <NAMESPACE> <code>`, "
        "`Unidentified controller`; known source labels do not establish "
        "hardware identity.", "",
        "## MQTT mapping", "",
        "All measurement and diagnostic states are non-retained. Discovery "
        "and availability are retained. Each protocol has independent "
        "freshness and all discovered sensors expire after 60 seconds. "
        "Live BLE reception is not implemented.", "",
    ])
    table(
        ("Meaning", "Topic pattern"),
        (
            ("J1939 raw frame", "vehicle/{vehicle}/j1939/{source}/frame"),
            ("J1939 measurement",
             "vehicle/{vehicle}/j1939/{source}/spn/{spn}"),
            ("J1939 diagnostic report",
             "vehicle/{vehicle}/j1939/{source}/faults/{pgn}"),
            ("J1587 normalized raw parameter",
             "vehicle/{vehicle}/j1587/{mid}/report"),
            ("J1587 measurement", "vehicle/{vehicle}/j1587/{mid}/pid/{pid}"),
            ("J1587 diagnostic entries",
             "vehicle/{vehicle}/j1587/{mid}/faults/194"),
            ("Protocol availability",
             "vehicle/{vehicle}/{j1939-or-j1587}/availability"),
        ),
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Print portable JSON; never infer controller profiles from model/year."""
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--export", action="store_true")
    action.add_argument("--markdown", action="store_true")
    action.add_argument("--namespace", choices=NAMESPACES)
    parser.add_argument("--output", type=Path, help="Markdown output file")
    parser.add_argument("--code")
    parser.add_argument(
        "--source", type=int, help="J1939 address or J1587 MID"
    )
    parser.add_argument("--fmi", type=int)
    parser.add_argument("--profile", choices=tuple(PROFILES))
    args = parser.parse_args(argv)
    if args.output is not None and not args.markdown:
        parser.error("--output requires --markdown")
    if args.export or args.markdown:
        if any(value is not None for value in (
            args.code, args.source, args.fmi, args.profile,
        )):
            parser.error("Export cannot be combined with lookup options")
        result = export_catalog()
    else:
        if args.code is None:
            parser.error("--code is required for a lookup")
        try:
            code = (
                args.code if args.namespace in (
                    "detroit_flash", "allison_wtec", "obd_pid",
                ) else int(args.code, 10)
            )
            if args.source is not None and not 0 <= args.source <= 255:
                raise ValueError("Source outside protocol range")
            if args.fmi is not None:
                if args.source is None:
                    parser.error("--source is required for a fault lookup")
                result = describe_fault(
                    args.namespace, code, args.fmi,
                    source=args.source, profile=args.profile,
                )
            else:
                result = lookup(
                    args.namespace, code,
                    source=args.source, profile=args.profile,
                )
        except ValueError as err:
            parser.error(str(err))
    if args.markdown:
        text = render_markdown(result)
        if args.output is not None:
            try:
                args.output.write_text(text, encoding="utf-8", newline="\n")
            except OSError as err:
                parser.exit(1, f"Cannot write Markdown catalog: {err}\n")
        else:
            print(text, end="")
    else:
        print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
