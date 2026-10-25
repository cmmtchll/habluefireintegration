"""Dictionary provenance, namespace isolation and human-facing annotations."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from custom_components.bluefire.catalog import (
    DETROIT_SIDS,
    FMIS,
    MANUFACTURER_CODES,
    PGNS,
    PROFILES,
    describe_fault,
    export_catalog,
    lookup,
    source_label,
    source_name,
)
from custom_components.bluefire.signals import SIGNALS
from custom_components.bluefire.telemetry import Frame, MqttBridge
from scripts.catalog_bluefire import main, render_markdown


class CatalogTests(unittest.TestCase):
    def test_export_has_unique_scoped_keys_and_provenance(self):
        catalog = json.loads(json.dumps(export_catalog(), allow_nan=False))
        self.assertEqual(catalog["catalog_version"], 2)
        self.assertEqual(len(catalog["measurements"]), 37)
        self.assertEqual(len(FMIS), 32)
        self.assertEqual(set(FMIS), set(range(32)))
        keys = [
            (item["profile"], item["namespace"], item["code"])
            for item in catalog["manufacturer_codes"]
        ]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(catalog["scoped_sids"]), len(DETROIT_SIDS))
        for item in catalog["manufacturer_codes"]:
            self.assertIn(item["profile"], PROFILES)
            self.assertTrue(item["name"])
            self.assertTrue(item["reference"].startswith("https://"))
            found = lookup(
                item["namespace"], item["code"], profile=item["profile"]
            )
            self.assertTrue(found["known"])
            self.assertEqual(found["name"], item["name"])
        for item in catalog["codes"]:
            self.assertTrue(item["known"])
            self.assertTrue(item["reference"])
        for signal in SIGNALS:
            self.assertIn(signal.pgn, PGNS)
            found = lookup("spn", signal.spn)
            self.assertEqual(found["name"], signal.name)
            self.assertEqual(found["unit"], signal.unit)
            self.assertIn(signal.unit, signal.description)
            self.assertTrue(signal.metadata()["description"])
        self.assertIn("revolutions per minute", SIGNALS[0].description)
        self.assertIn(
            "500 HP", PROFILES["detroit_ddec_iii_iv"]["applicability"]
        )

    def test_protocol_namespaces_are_not_interchangeable(self):
        self.assertEqual(lookup("spn", 190)["name"], "Engine speed")
        self.assertEqual(lookup("pid", 190)["name"], "Engine speed")
        self.assertFalse(lookup("sid", 190, source=128)["known"])
        self.assertFalse(lookup("spn", 12)["known"])
        self.assertEqual(lookup("obd_pid", "01:0C")["name"], "Engine speed")
        self.assertEqual(lookup("obd_pid", "01:0C")["unit"], "rpm")
        self.assertFalse(lookup("obd_pid", "02:0C")["known"])
        self.assertFalse(lookup("pid", 12)["known"])
        coolant = lookup("pid", 110)
        self.assertEqual(coolant["unit"], "°C")
        self.assertEqual(coolant["unit_basis"], "preferred_display_unit_only")
        self.assertEqual(lookup("spn", 110)["unit_basis"], "engineering_unit")
        self.assertEqual(source_name(3), "Transmission")
        self.assertEqual(source_name(130, j1587=True), "Transmission")
        self.assertEqual(source_name(130), "Unidentified controller")
        self.assertEqual(source_label(23), "Instrument cluster (23)")
        unknown = lookup("spn", 500000)
        self.assertFalse(unknown["known"])
        self.assertIn("500000", unknown["name"])
        self.assertIsNone(unknown["reference"])

    def test_controller_specific_codes_require_explicit_profiles(self):
        self.assertFalse(lookup("detroit_flash", "21")["known"])
        self.assertFalse(lookup(
            "allison_wtec", "13-12", profile="detroit_ddec_iii_iv"
        )["known"])
        low = lookup(
            "allison_wtec", "13-13", profile="allison_wtec_iii"
        )
        # 13-13 is moderately LOW, not the high-voltage code 13-23.
        self.assertIn("moderately low", low["name"])
        self.assertIn("high", lookup(
            "allison_wtec", "13-23", profile="allison_wtec_iii"
        )["name"])
        self.assertFalse(lookup(
            "allison_wtec", "99-99", profile="allison_wtec_iii"
        )["known"])

    def test_detroit_equivalents_do_not_leak_across_ecus_or_namespaces(self):
        for namespace, code, fmi in (("pid", 91, 3), ("sid", 1, 0)):
            result = describe_fault(
                namespace, code, fmi, source=128,
                profile="detroit_ddec_iii_iv",
            )
            self.assertTrue(result["known"])
            self.assertEqual(len(result["manufacturer_matches"]), 1)
            if namespace == "sid":
                self.assertIn("Injector response too slow",
                              result["description"])
            for source, profile in (
                (130, "detroit_ddec_iii_iv"), (128, None),
                (128, "allison_wtec_iii"),
            ):
                result = describe_fault(
                    namespace, code, fmi, source=source, profile=profile
                )
                self.assertEqual(result["manufacturer_matches"], [])
        self.assertFalse(lookup(
            "sid", 1, source=130, profile="detroit_ddec_iii_iv"
        )["known"])
        self.assertEqual(describe_fault(
            "spn", 91, 3, source=0, profile="detroit_ddec_iii_iv"
        )["manufacturer_matches"], [])
        for item in MANUFACTURER_CODES:
            for namespace, pairs in (
                ("pid", item.pid_fmi), ("sid", item.sid_fmi),
            ):
                for code, fmi in pairs:
                    found = describe_fault(
                        namespace, code, fmi,
                        source=128, profile=item.profile,
                    )
                    self.assertTrue(found["known"])
                    self.assertIn(
                        item.code,
                        [m["code"] for m in found["manufacturer_matches"]],
                    )

    def test_invalid_code_inputs_are_explicit_errors(self):
        for namespace, code, options in (
            ("not-a-namespace", 1, {}), ("spn", True, {}),
            ("pid", -1, {}), ("pid", 1024, {}), ("sid", 512, {}),
            ("spn", 0x80000, {}), ("pgn", 0x40000, {}),
            ("fmi", 32, {}), ("spn", "190", {}),
            ("allison_wtec", "1312", {}), ("detroit_flash", "123", {}),
            ("obd_pid", "01:100", {}), ("spn", 190, {"profile": "ddec_v"}),
            ("sid", 1, {"source": -1}), ("sid", 1, {"source": True}),
        ):
            with self.subTest(namespace=namespace, code=code):
                with self.assertRaises(ValueError):
                    lookup(namespace, code, **options)
        for namespace, fmi in (
            ("command", 3), ("pid", 16), ("sid", -1),
            ("spn", 32), ("spn", True),
        ):
            with self.assertRaises(ValueError):
                describe_fault(namespace, 1, fmi, source=128)

    def test_cli_export_lookup_and_rejected_combinations(self):
        for args in (
            ["--export"],
            ["--namespace", "spn", "--code", "190"],
            ["--namespace", "pid", "--code", "91", "--fmi", "3",
             "--source", "128", "--profile", "detroit_ddec_iii_iv"],
            ["--namespace", "allison_wtec", "--code", "13-12",
             "--profile", "allison_wtec_iii"],
        ):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(args), 0)
            self.assertIsInstance(json.loads(output.getvalue()), dict)
        for args in (
            [], ["--namespace", "spn"],
            ["--export", "--code", "190"],
            ["--namespace", "spn", "--code", "invalid"],
            ["--namespace", "pid", "--code", "91", "--fmi", "3"],
            ["--namespace", "pid", "--code", "91", "--source", "256"],
            ["--namespace", "spn", "--code", "999999"],
            ["--export", "--output", "unused.md"],
            ["--markdown", "--code", "190"],
        ):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(args)

    def test_markdown_reference_matches_every_catalog_definition(self):
        catalog = export_catalog()
        rendered = render_markdown(catalog)
        path = (
            Path(__file__).resolve().parents[1]
            / "docs" / "code-reference.md"
        )
        self.assertEqual(path.read_text(encoding="utf-8"), rendered)
        for record in catalog["codes"]:
            self.assertIn(record["name"], rendered)
        for record in catalog["manufacturer_codes"]:
            self.assertIn(record["code"], rendered)
            self.assertIn(record["name"], rendered)
            self.assertIn(record["reference"], rendered)
        for signal in (
            catalog["measurements"] + catalog["j1587_measurements"]
        ):
            self.assertIn(signal["name"], rendered)
            self.assertIn(signal["description"], rendered)
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--markdown"]), 0)
        self.assertEqual(output.getvalue(), rendered)
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "catalog.md"
            self.assertEqual(main([
                "--markdown", "--output", str(output_path),
            ]), 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"),
                             rendered)
            self.assertNotIn(b"\r\n", output_path.read_bytes())
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(["--markdown", "--output", directory])


class AnnotationPublishingTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_measurement_labels_ids_and_units(self):
        publish = AsyncMock()
        bridge = MqttBridge("coach", publish)
        for pgn in {signal.pgn for signal in SIGNALS}:
            await bridge.async_process_frame(Frame(
                (6 << 26) | (pgn << 8), bytes(8)
            ))
        messages = {
            topic: (json.loads(payload), retain)
            for topic, payload, retain in (
                call.args for call in publish.await_args_list
            ) if payload not in ("online", "offline")
        }
        for signal in SIGNALS:
            state, retain = messages[
                f"vehicle/coach/j1939/0/spn/{signal.spn}"
            ]
            self.assertFalse(retain)
            for key, value in signal.metadata().items():
                self.assertEqual(state[key], value)
            self.assertEqual(state["source_name"], "Engine")
            self.assertEqual(state["pgn_name"], PGNS[signal.pgn])
            config, retain = messages[
                "homeassistant/sensor/"
                f"bluefire_coach_0_{signal.spn}/config"
            ]
            self.assertTrue(retain)
            self.assertEqual(config["unit_of_measurement"], signal.unit)
            self.assertEqual(
                config["name"], f"{signal.name} - Engine (0)"
            )
            self.assertIn("description", config["json_attributes_template"])
            self.assertEqual(
                config["unique_id"], f"bluefire_coach_0_{signal.spn}"
            )
