"""Curated code dictionary; identifiers never cross protocol namespaces.

Labels are independently worded factual summaries, not vendor resource tables.
Coverage and provenance are exported with the database. Unknown stays unknown.
"""

from dataclasses import asdict, dataclass
import re

from .signals import SIGNALS

CATALOG_VERSION = 3
REFERENCES = {
    "bluefire": (
        "Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; "
        "J1939/J1708 enums and FaultDescriptions namespace boundaries. "
        "Default source roles are hints, not ECU identity verification."
    ),
    "j1939": (
        "https://www.csselectronics.com/pages/"
        "j1939-73-dm1-diagnostic-message-dtc"
    ),
    "fmi": "https://j1939hub.com/fmi-decoder/",
    "obd": (
        "https://www.csselectronics.com/pages/"
        "obd2-pid-table-on-board-diagnostics-j1979"
    ),
    "signals": (
        "https://github.com/canboat/canboat/tree/"
        "3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns"
    ),
    "wtec": (
        "https://assets.wellertruck.com/reference-materials/"
        "troubleshooting-manuals/wteclllshiftselectormanual.pdf"
    ),
    "ddec": (
        "https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/"
    ),
    "ddec_appendix": (
        "https://manualmachine.com/detroitdiesel/ddeciv/24330624-user-manual/"
    ),
    "prevost": (
        "https://github.com/cmmtchll/LibertyH3-45ElegantLady2003RV/blob/main/"
        "manuals/extracted/master-set/"
        "manuals-maintenance-manual-pa1163-2003.md"
    ),
    "j1587": (
        "Local Windows BlueFire 12.5.6 J1708 parameter scaling cross-check, "
        "including unsigned quarter-degree Fahrenheit temperatures and "
        "signed crankcase pressure; independent native-unit conversions. "
        "Datalink/diagnostic structure: "
        "https://github.com/ainfosec/pretty_j1587"
    ),
}
PROFILES = {
    "detroit_ddec_iii_iv": {
        "name": "Detroit Diesel DDEC III/IV",
        "applicability": (
            "DDEC III/IV single-ECM reference (6SE497). The coach's official "
            "labels and Prevost PA1163 identify its 500 HP Series 60 and "
            "DDEC IV; select the confirmed engine profile in configuration. "
            "Other installations remain standard J1587 unless selected."
        ),
        "coverage": (
            "All 66 flash-code sections indexed by the referenced 6SE497 "
            "edition, with independently summarized labels and verified "
            "equivalents. Conflicting/ambiguous crosswalks are withheld, "
            "not guessed. Gas, EGR, ESS, Optimized Idle and optional sensor "
            "references do not establish installed equipment or calibration."
        ),
        "reference": REFERENCES["ddec"],
    },
    "allison_wtec_iii": {
        "name": "Allison B500 with WTEC III controls",
        "applicability": (
            "B500 only when WTEC III controls are confirmed. Not WTEC II "
            "or Allison 4th/5th-generation P-codes; no automatic selection."
        ),
        "coverage": "Curated two-part selector codes, not all calibrations.",
        "reference": REFERENCES["wtec"],
    },
}

PGNS = {
    59904: "Parameter group request",
    60160: "Transport protocol data transfer",
    60416: "Transport protocol connection management",
    60928: "Address claim",
    61443: "Electronic engine controller 2",
    61444: "Electronic engine controller 1",
    65226: "Active diagnostic faults",
    65227: "Previously active diagnostic faults",
    65244: "Engine idle operation",
    65248: "Vehicle distance",
    65253: "Engine hours and revolutions",
    65257: "Fuel consumption",
    65262: "Engine temperature",
    65263: "Engine fluid levels and pressures",
    65265: "Cruise control and vehicle speed",
    65266: "Fuel economy",
    65269: "Ambient conditions",
    65270: "Engine inlet and exhaust conditions",
    65271: "Vehicle electrical power",
    65272: "Transmission fluids",
    65276: "Vehicle fluids",
}
SOURCES = {
    0: "Engine", 1: "Engine 2", 3: "Transmission", 11: "Brakes",
    15: "Retarder", 17: "Cruise control", 23: "Instrument cluster",
    25: "Climate control", 33: "Body controller", 49: "Cab controller",
    51: "Tire pressure monitor", 61: "Exhaust system",
    85: "Aftertreatment", 254: "Null address", 255: "Global address",
}
MIDS = {
    128: "Engine", 130: "Transmission", 136: "Brakes",
    140: "Instrument cluster", 142: "Vehicle management",
    146: "Climate control", 171: "Driver information", 249: "Body controller",
}
PIDS = {
    26: "Fan speed percentage", 40: "Retarder switch",
    68: "Engine torque factor", 73: "External pump pressure",
    74: "Maximum road speed", 81: "Exhaust back pressure",
    51: "Throttle position", 70: "Parking brake status",
    84: "Vehicle speed", 85: "Cruise control status",
    86: "Cruise set speed", 91: "Accelerator pedal position",
    92: "Engine load", 93: "Actual engine torque",
    94: "Fuel delivery pressure", 95: "Fuel inlet restriction",
    96: "Fuel level", 98: "Engine oil level", 99: "Oil filter restriction",
    100: "Engine oil pressure", 101: "Crankcase pressure",
    102: "Intake manifold pressure", 103: "Turbocharger speed",
    105: "Intake manifold temperature", 106: "Air inlet pressure",
    107: "Air filter restriction",
    108: "Barometric pressure", 109: "Coolant pressure",
    110: "Coolant temperature", 111: "Coolant level",
    116: "Brake application pressure", 117: "Primary brake air pressure",
    118: "Secondary brake air pressure", 120: "Retarder oil temperature",
    121: "Engine retarder status", 122: "Retarder torque percentage",
    154: "Legacy EGR temperature", 155: "Legacy EGR differential pressure",
    162: "Transmission selected gear", 163: "Transmission current gear",
    168: "Electrical system voltage", 171: "Ambient air temperature",
    172: "Engine air intake temperature", 173: "Exhaust gas temperature",
    174: "Fuel temperature",
    175: "Engine oil temperature", 177: "Transmission oil temperature",
    183: "Fuel rate", 184: "Instantaneous fuel economy",
    185: "Average fuel economy", 187: "Variable speed governor input",
    190: "Engine speed",
    192: "Multisection parameter", 194: "Diagnostic trouble codes",
    195: "Diagnostic clearing request", 196: "Diagnostic clearing response",
    222: "Anti-theft status",
    234: "Software identification", 235: "Engine idle hours",
    236: "Engine idle fuel used", 237: "Vehicle identification",
    243: "Component identification", 245: "Total vehicle distance",
    247: "Total engine hours", 250: "Total fuel used",
    251: "Clock module", 252: "Clock module extension",
    351: "Turbo compressor inlet temperature", 354: "Relative humidity",
    404: "Turbo compressor outlet temperature",
    411: "EGR differential pressure", 412: "EGR temperature",
    439: "Extended intake manifold pressure",
}
PID_REFERENCES = {
    pid: f"{REFERENCES['ddec']}40{flash:02x}02.html"
    for pid, flash in (
        (73, 86), (81, 77), (95, 37), (98, 81), (99, 66), (103, 64),
        (106, 47), (107, 65), (154, 48), (155, 48), (187, 11), (222, 77),
        (251, 77), (252, 77), (351, 29), (354, 17), (404, 29), (411, 48),
        (412, 48),
    )
}
FMIS = {
    0: "Above normal range (most severe)",
    1: "Below normal range (most severe)",
    2: "Erratic, intermittent or incorrect data",
    3: "Voltage high or short to high supply",
    4: "Voltage low or short to low supply",
    5: "Current low or open circuit",
    6: "Current high or grounded circuit",
    7: "Mechanical system not responding correctly",
    8: "Abnormal frequency, pulse width or period",
    9: "Abnormal update rate",
    10: "Abnormal rate of change",
    11: "Root cause not identified",
    12: "Faulty intelligent device or component",
    13: "Calibration required",
    14: "Special instructions required",
    15: "Above normal range (least severe)",
    16: "Above normal range (moderately severe)",
    17: "Below normal range (least severe)",
    18: "Below normal range (moderately severe)",
    19: "Received network data contains an error",
    20: "Data drifted high", 21: "Data drifted low",
    **{code: "Reserved failure mode" for code in range(22, 31)},
    31: "Condition exists",
}
J1587_FMIS = {
    **{code: FMIS[code] for code in range(15)},
    11: "Failure mode not identifiable",
    15: "Reserved failure mode",
}
LAMP_STATUS = {0: "Off", 1: "On", 2: "Reserved", 3: "Unavailable"}
LAMP_FLASH = {
    0: "Slow flash", 1: "Fast flash", 2: "Reserved", 3: "Unavailable",
}
COMMANDS = {
    7: "J1708 availability",
    151: "J1939 parameter group report", 154: "J1587 parameter report",
    169: "Authentication", 174: "OBD report",
    177: "Firmware/build date response (app-version dependent)",
    201: "Arbitration identifier response", 255: "Heartbeat",
}
SPNS = {signal.spn: signal.name for signal in SIGNALS}
SPNS.update({
    116: "Brake application pressure", 117: "Primary brake air pressure",
    118: "Secondary brake air pressure", 120: "Retarder oil temperature",
    623: "Red stop lamp", 624: "Amber warning lamp",
    987: "Protect lamp", 1213: "Malfunction indicator lamp",
})
OBD_PIDS = {
    "01:05": "Engine coolant temperature", "01:0C": "Engine speed",
    "01:0D": "Vehicle speed", "01:0F": "Intake air temperature",
    "01:10": "Mass air flow", "01:11": "Throttle position",
}
OBD_UNITS = {
    "01:05": "°C", "01:0C": "rpm", "01:0D": "km/h",
    "01:0F": "°C", "01:10": "g/s", "01:11": "%",
}
PID_UNITS = {
    26: "%", 68: "%", 74: "km/h", 86: "km/h", 122: "%",
    184: "km/L", 185: "km/L", 439: "kPa",
    51: "%", 84: "km/h", 91: "%", 92: "%",
    93: "%", 94: "kPa", 96: "%", 100: "kPa", 101: "kPa", 102: "kPa",
    105: "°C", 108: "kPa", 109: "kPa", 110: "°C", 111: "%",
    116: "kPa", 117: "kPa", 118: "kPa", 120: "°C", 168: "V",
    171: "°C", 172: "°C", 173: "°C", 174: "°C", 175: "°C", 177: "°C",
    183: "L/h", 190: "rpm", 235: "h", 236: "L", 245: "km",
    247: "h", 250: "L",
}


@dataclass(frozen=True)
class ManufacturerCode:
    """One profile-scoped reference; never a globally meaningful integer."""

    profile: str
    namespace: str
    code: str
    name: str
    reference: str
    pid_fmi: tuple[tuple[int, int], ...] = ()
    sid_fmi: tuple[tuple[int, int], ...] = ()
    applicability: str = ""


def _detroit(
    code: int, name: str, *pairs: tuple[int, int],
    sids: tuple[tuple[int, int], ...] = (), applicability: str = "",
):
    return ManufacturerCode(
        "detroit_ddec_iii_iv", "detroit_flash", str(code), name,
        f"{REFERENCES['ddec']}40{code:02x}02.html", pairs, sids, applicability,
    )


def _allison(code: str, name: str):
    return ManufacturerCode(
        "allison_wtec_iii", "allison_wtec", code, name, REFERENCES["wtec"],
    )


def _detroit_sid(code: int, name: str, *pairs: tuple[int, int]):
    return ManufacturerCode(
        "detroit_ddec_iii_iv", "detroit_flash", str(code), name,
        f"{REFERENCES['ddec']}40{code:02x}02.html", sid_fmi=pairs,
    )


MANUFACTURER_CODES = (
    _detroit(11, "Variable speed governor input voltage low", (187, 4)),
    _detroit(12, "Variable speed governor input voltage high", (187, 3)),
    _detroit(13, "Coolant level sensor circuit low", (111, 4), (111, 6)),
    _detroit(14, "Coolant or oil temperature sensor circuit high",
             (110, 3), (175, 3)),
    _detroit(15, "Coolant or oil temperature sensor circuit low",
             (110, 4), (175, 4)),
    _detroit(16, "Coolant level sensor circuit high", (111, 3), (111, 5)),
    _detroit(17, "Throttle plate or humidity input voltage high",
             (51, 3), (354, 3), applicability="Application-dependent sensors"),
    _detroit(18, "Throttle plate or humidity input voltage low",
             (51, 4), (354, 4), applicability="Application-dependent sensors"),
    _detroit(21, "Throttle position sensor circuit high", (91, 3)),
    _detroit(22, "Throttle position sensor circuit low", (91, 4)),
    _detroit(23, "Fuel temperature sensor circuit high", (174, 3)),
    _detroit(24, "Fuel temperature sensor circuit low", (174, 4)),
    _detroit_sid(26, "Auxiliary engine shutdown input active",
                 (25, 11), (61, 11)),
    _detroit(27, "Air inlet temperature input voltage high", (172, 3)),
    _detroit(28, "Air inlet temperature input voltage low", (172, 4)),
    _detroit(29, "Turbo compressor temperature input voltage low",
             (351, 4), (404, 4), applicability="Optional turbo/EGR sensors"),
    _detroit_sid(31, "Engine brake output circuit fault",
                 (51, 3), (51, 4), (52, 3), (52, 4)),
    _detroit_sid(32, "Stop or check engine lamp circuit fault",
                 (238, 3), (238, 4), (239, 3), (239, 4)),
    _detroit(33, "Boost pressure input voltage high", (102, 3)),
    _detroit(34, "Boost pressure input voltage low", (102, 4)),
    _detroit(35, "Oil pressure input voltage high", (100, 3)),
    _detroit(36, "Oil pressure input voltage low", (100, 4)),
    _detroit(37, "Fuel pressure or restriction input voltage high",
             (94, 3), (95, 3)),
    _detroit(38, "Fuel pressure or restriction input voltage low",
             (94, 4), (95, 4)),
    _detroit(39, "EGR valve or variable-nozzle turbo response fault",
             sids=((146, 2), (146, 12), (146, 7), (152, 7),
                   (147, 2), (147, 12), (147, 14), (147, 11),
                   (147, 7), (153, 7)),
             applicability="EGR/VNT applications only; not assumed installed"),
    _detroit_sid(41, "Missing timing reference or extra synchronous pulses",
                 (21, 0)),
    _detroit_sid(42, "Missing synchronous reference or extra timing pulses",
                 (21, 1)),
    _detroit(43, "Coolant level below normal", (111, 1)),
    _detroit(44, "Coolant or engine oil temperature above normal",
             (110, 0), (175, 0)),
    _detroit(45, "Engine oil pressure below normal", (100, 1)),
    _detroit(46, "ECM battery supply voltage low", (168, 1)),
    _detroit(47, "Fuel, boost or gas-engine inlet pressure above range",
             (94, 0), (102, 0), (106, 0)),
    _detroit(48, "Fuel pressure or optional inlet/EGR data below range",
             (94, 1), (106, 1), (412, 1), (154, 1), (411, 1), (155, 1),
             (351, 1), (404, 1),
             applicability="EGR PID numbering depends on ECM software"),
    _detroit(49, "Turbo compressor temperature above range or derate",
             (351, 0), (404, 0), (404, 14)),
    _detroit(51, "Turbo compressor temperature input voltage high",
             (351, 3), (404, 3)),
    _detroit_sid(52, "ECM analog-to-digital conversion fault", (254, 12)),
    _detroit_sid(53, "Engine controller nonvolatile memory error",
                 (253, 12), (253, 2)),
    _detroit(54, "Vehicle speed signal fault", (84, 12)),
    _detroit_sid(55, "J1939 link or other-controller communication fault",
                 (231, 12), (216, 14)),
    _detroit_sid(56, "J1587 diagnostic data link fault", (250, 12)),
    _detroit_sid(57, "J1922 data link fault", (249, 12)),
    _detroit(58, "Engine torque overload", (92, 0)),
    _detroit_sid(61, "Injector response too slow",
                 *((cylinder, 0) for cylinder in range(1, 7))),
    _detroit_sid(62, "Auxiliary output open or short to supply",
                 *((sid, fmi) for sid in (26, 40, 53, 54, 55, 56)
                   for fmi in (3, 4))),
    _detroit_sid(63, "PWM output open or short to supply",
                 *((sid, fmi) for sid in range(57, 61) for fmi in (3, 4))),
    _detroit(64, "Turbo speed excessive or speed sensor failure",
             (103, 0), (103, 8), applicability="Turbo speed sensor required"),
    _detroit(65, "Air filter sensor or gas-engine throttle response fault",
             (107, 3), (107, 4), (51, 0), (51, 1), (51, 7)),
    _detroit(66, "Oil filter sensor or gas-engine knock sensor fault",
             (99, 3), (99, 4),
             sids=((76, 0), (76, 7), (76, 3), (76, 4))),
    _detroit(67, "Coolant pressure or gas-engine inlet pressure circuit fault",
             (109, 3), (109, 4), (106, 3), (106, 4)),
    _detroit_sid(68, "Throttle idle-validation circuit fault",
                 (230, 5), (230, 6)),
    _detroit_sid(71, "Injector response too fast",
                 *((cylinder, 1) for cylinder in range(1, 7))),
    _detroit(72, "Vehicle overspeed", (84, 0), (84, 11)),
    _detroit(73, "Air restriction, ESS shift input or gas valve fault",
             sids=((227, 2), (227, 3), (227, 4), (226, 11), (151, 14),
                   (77, 0), (77, 1), (77, 3), (77, 4)),
             applicability=(
                 "ESS/gas options are not assumed. Air restriction 107/0 "
                 "is omitted: 6SE497 says SID, 7SA743 Appendix A says PID."
             )),
    _detroit(74, "Optimized Idle interlock or oil filter restriction fault",
             applicability=(
                 "Equivalence withheld: 6SE497 reports PID 70/4 and an "
                 "Optimized Idle interlock; 7SA743 reports PID 99/0. "
                 "Select the applicable calibration/service reference."
             )),
    _detroit(75, "ECM battery supply voltage high", (168, 0)),
    _detroit(76, "Engine overspeed with engine brake", (121, 0)),
    _detroit(77, "Application-specific range, clock or anti-theft fault",
             (73, 1), (81, 0), (81, 1), (81, 12), (81, 3), (81, 4),
             (95, 1), (99, 1), (100, 0), (102, 1), (105, 1), (107, 1),
             (108, 0), (108, 1), (109, 0), (110, 1), (111, 0), (171, 0),
             (171, 1), (172, 1), (175, 1), (222, 14), (251, 10),
             (251, 13), (252, 10), (252, 13), (354, 0), (354, 1),
             applicability=(
                 "Many entries are not on-highway Series 60 features. "
                 "PID 174/0 and 174/1 withheld: the guide assigns both "
                 "fuel temperature and temporary TCO meanings."
             )),
    _detroit(78, "Cruise or adaptive-cruise system fault", (86, 14)),
    _detroit(81, "Oil level or exhaust/EGR sensor input voltage high",
             (98, 3), (173, 3),
             applicability=(
                 "EGR equivalents withheld because the source editions "
                 "disagree on PID/SID namespace and legacy numbering."
             )),
    _detroit(82, "Oil level or exhaust/EGR sensor input voltage low",
             (98, 4), (173, 4),
             applicability="EGR crosswalk withheld; see flash 81 notes"),
    _detroit(83, "Exhaust temperature, pump pressure or EGR value high",
             (173, 0), (73, 0),
             applicability="EGR crosswalk withheld; see flash 81 notes"),
    _detroit(84, "Engine oil level low", (98, 1)),
    _detroit(85, "Engine overspeed", (190, 0)),
    _detroit(86, "External pump pressure input voltage high", (73, 3)),
    _detroit(87, "External pump pressure input voltage low", (73, 4)),
    _detroit(89, "Fuel restriction or maintenance coolant-level fault",
             (95, 0), (111, 12)),
    _allison("13-12", "Transmission controller supply voltage low"),
    _allison("13-13", "Transmission controller supply voltage moderately low"),
    _allison("13-23", "Transmission controller supply voltage high"),
    _allison("14-12", "Transmission oil level sensor signal low"),
    _allison("14-23", "Transmission oil level sensor signal high"),
    _allison("21-12", "Transmission throttle position signal low"),
    _allison("21-23", "Transmission throttle position signal high"),
    _allison("22-14", "Transmission engine speed sensor fault"),
    _allison("22-15", "Transmission turbine speed sensor fault"),
    _allison("22-16", "Transmission output speed sensor fault"),
    _allison("23-12", "Primary transmission selector fault"),
    _allison("23-13", "Primary transmission selector mode fault"),
    _allison("23-14", "Secondary transmission selector fault"),
    _allison("23-15", "Secondary transmission selector mode fault"),
    _allison("23-16", "Transmission selector display connection fault"),
    _allison("24-12", "Transmission sump fluid temperature below range"),
    _allison("24-23", "Transmission sump fluid temperature above range"),
    _allison("26-00", "Transmission cannot detect throttle data source"),
    _allison("26-11", "Transmission cannot detect engine coolant data source"),
    _allison("33-12", "Transmission sump temperature sensor signal low"),
    _allison("33-23", "Transmission sump temperature sensor signal high"),
)
DETROIT_SIDS = {
    **{
        cylinder: (f"Engine injector {cylinder}",
                   f"{REFERENCES['ddec']}403d01.html")
        for cylinder in range(1, 7)
    },
    253: ("Engine controller nonvolatile memory",
          f"{REFERENCES['ddec']}403501.html"),
    **{
        sid: (name, f"{REFERENCES['ddec']}40{flash:02x}02.html")
        for sid, name, flash in (
            (21, "Engine timing and synchronous reference sensors", 41),
            (25, "Auxiliary shutdown input 1", 26),
            (61, "Auxiliary shutdown input 2", 26),
            (51, "Engine brake output 1", 31),
            (52, "Engine brake output 2", 31),
            (76, "Gas-engine knock sensor", 66),
            (77, "Gas metering valve", 73),
            (146, "EGR valve", 39), (147, "Variable-nozzle turbo vanes", 39),
            (152, "Legacy EGR valve response", 39),
            (153, "Legacy turbo vane response", 39),
            (151, "ESS transmission gear state", 73),
            (216, "Other-controller communications", 55),
            (226, "ESS neutral switch", 73),
            (227, "ESS shift knob", 73),
            (230, "Throttle idle-validation switch", 68),
            (231, "J1939 data link", 55),
            (238, "Stop engine lamp circuit", 32),
            (239, "Check engine lamp circuit", 32),
            (249, "J1922 data link", 57), (250, "J1587 data link", 56),
            (254, "ECM analog-to-digital converter", 52),
        )
    },
    **{
        sid: (f"Auxiliary output {output}",
              f"{REFERENCES['ddec']}403e02.html")
        for sid, output in ((26, 1), (40, 2), (53, 5), (54, 6), (55, 7),
                            (56, 8))
    },
    **{
        sid: (f"PWM output {sid - 56}", f"{REFERENCES['ddec']}403f02.html")
        for sid in range(57, 61)
    },
}

NAMESPACES = (
    "pgn", "spn", "source", "mid", "pid", "sid", "fmi", "command",
    "obd_pid", "detroit_flash", "allison_wtec",
)


def source_name(source: int, *, j1587: bool = False) -> str:
    """Address roles are conventional hints, not discovered ECU identities."""
    labels = MIDS if j1587 else SOURCES
    return labels.get(source, "Unidentified controller")


def source_label(source: int) -> str:
    """Distinguish controllers without numeric-only names."""
    return f"{source_name(source)} ({source})"


def lookup(
    namespace: str, code: int | str, *, profile: str | None = None,
    source: int | None = None,
) -> dict:
    """SID mappings require MID/profile; OBD PID keys include the mode."""
    if namespace not in NAMESPACES:
        raise ValueError("Unknown code namespace")
    if profile is not None and profile not in PROFILES:
        raise ValueError("Unknown controller profile")
    if source is not None and (
        type(source) is not int or not 0 <= source <= 255
    ):
        raise ValueError("Source outside protocol range")
    if namespace in ("allison_wtec", "detroit_flash", "obd_pid"):
        pattern = {
            "allison_wtec": r"\d{2}-\d{2}",
            "detroit_flash": r"\d{1,2}",
            "obd_pid": r"[0-9A-F]{2}:[0-9A-F]{2}",
        }[namespace]
        if not re.fullmatch(pattern, str(code), flags=re.ASCII):
            raise ValueError("Invalid namespaced code format")
    else:
        maximum = {
            "source": 255, "mid": 255, "fmi": 31, "command": 255,
            "pid": 1023, "sid": 511, "spn": 0x7FFFF, "pgn": 0x3FFFF,
        }[namespace]
        if type(code) is not int or not 0 <= code <= maximum:
            raise ValueError("Code outside namespace range")
    tables = {
        "pgn": PGNS, "spn": SPNS, "source": SOURCES, "mid": MIDS,
        "pid": PIDS, "fmi": FMIS, "command": COMMANDS,
        "obd_pid": OBD_PIDS,
    }
    name = tables.get(namespace, {}).get(code)
    reference = REFERENCES["bluefire"]
    if namespace == "fmi":
        reference = REFERENCES["fmi"]
    elif namespace == "obd_pid":
        reference = REFERENCES["obd"]
    elif namespace == "pid" and code in PID_REFERENCES:
        reference = PID_REFERENCES[code]
    elif namespace in ("spn", "pgn"):
        reference = (
            REFERENCES["j1939"] if code in (65226, 65227, 623, 624, 987, 1213)
            else REFERENCES["signals"]
        )
    if (
        namespace == "sid" and source == 128
        and profile == "detroit_ddec_iii_iv" and code in DETROIT_SIDS
    ):
        name, reference = DETROIT_SIDS[code]
    for item in MANUFACTURER_CODES:
        if (item.namespace, item.code, item.profile) == (
            namespace, str(code), profile,
        ):
            name, reference = item.name, item.reference
    units = {
        "spn": {signal.spn: signal.unit for signal in SIGNALS},
        "pid": PID_UNITS, "obd_pid": OBD_UNITS,
    }
    return {
        "namespace": namespace, "code": code, "profile": profile,
        "source": source, "known": name is not None,
        "name": name or f"Unmapped {namespace.upper()} {code}",
        "description": name or (
            "No verified mapping in this catalog; retain the identifier "
            "and use the controller-specific service reference."
        ),
        "reference": reference if name else None,
        "unit": units.get(namespace, {}).get(code),
        "unit_basis": (
            "preferred_display_unit_only" if namespace == "pid" else
            "engineering_unit"
        ) if code in units.get(namespace, {}) else None,
    }


def describe_fault(
    namespace: str, code: int, fmi: int, *, source: int,
    profile: str | None = None,
) -> dict:
    """Annotate a DTC without conflating a J1587 SID, PID or J1939 SPN."""
    if namespace not in ("spn", "pid", "sid"):
        raise ValueError("Expected SPN, PID or SID fault namespace")
    if type(fmi) is not int or not 0 <= fmi <= (
        31 if namespace == "spn" else 15
    ):
        raise ValueError("FMI outside protocol range")
    record = lookup(namespace, code, source=source, profile=profile)
    failure_mode = (
        FMIS[fmi] if namespace == "spn" else J1587_FMIS[fmi]
    )
    matches = [
        asdict(item) for item in MANUFACTURER_CODES
        if source == 128 and item.profile == profile
        and (code, fmi) in (
            item.pid_fmi if namespace == "pid" else
            item.sid_fmi if namespace == "sid" else ()
        )
    ]
    detail = (
        "; ".join(item["name"] for item in matches)
        if matches else failure_mode
    )
    return {
        **record, "fmi": fmi, "failure_mode": failure_mode,
        "parameter_unit": record["unit"], "unit": None, "unit_basis": None,
        "description": f"{record['name']}: {detail}",
        "source_name": source_name(source, j1587=namespace != "spn"),
        "manufacturer_matches": matches,
    }


def export_catalog() -> dict:
    """Export the auditable database without loading any vendor resources."""
    from .j1587 import READABLE_PIDS, STATUS_PARAMETERS, export_parameters

    tables = {
        "pgn": PGNS, "spn": SPNS, "source": SOURCES, "mid": MIDS,
        "pid": PIDS, "fmi": FMIS, "command": COMMANDS,
        "obd_pid": OBD_PIDS,
    }
    return {
        "catalog_version": CATALOG_VERSION,
        "coverage": "Curated, incomplete; unknown codes are not inferred.",
        "references": REFERENCES, "profiles": PROFILES,
        "measurements": [
            {**asdict(signal), "description": signal.description}
            for signal in SIGNALS
        ],
        "j1587_measurements": export_parameters(),
        "j1587_statuses": [
            {**asdict(p), "name": p.name, "length": p.length}
            for p in STATUS_PARAMETERS
        ],
        "j1587_readable_pids": sorted(READABLE_PIDS),
        "j1587_failure_modes": J1587_FMIS,
        "j1939_lamp_status": LAMP_STATUS,
        "j1939_lamp_flash": LAMP_FLASH,
        "codes": [
            lookup(namespace, code)
            for namespace, table in tables.items() for code in sorted(table)
        ],
        "manufacturer_codes": [asdict(item) for item in MANUFACTURER_CODES],
        "scoped_sids": [
            lookup("sid", code, source=128, profile="detroit_ddec_iii_iv")
            for code in sorted(DETROIT_SIDS)
        ],
    }
