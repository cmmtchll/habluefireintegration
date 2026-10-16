"""Audit BlueFire against Home Assistant's full integration quality scale."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

_TIERS: dict[str, tuple[tuple[str, str], ...]] = {
    "Bronze": (
        ("action-setup", "Service actions are registered in async_setup"),
        ("appropriate-polling", "Appropriate polling interval when polling"),
        ("brands", "Branding assets are available"),
        ("common-modules", "Common patterns are in common modules"),
        ("config-flow-test-coverage", "Full config-flow test coverage"),
        (
            "config-flow",
            "UI config flow, field descriptions, and config data/options",
        ),
        ("dependency-transparency", "Dependencies are transparent"),
        ("docs-actions", "Documentation describes service actions"),
        ("docs-triggers", "Documentation describes triggers"),
        ("docs-conditions", "Documentation describes conditions"),
        (
            "docs-high-level-description",
            "Documentation has a high-level description",
        ),
        (
            "docs-installation-instructions",
            "Documentation has installation steps",
        ),
        (
            "docs-removal-instructions",
            "Documentation has removal instructions",
        ),
        (
            "entity-event-setup",
            "Entity events use the correct lifecycle methods",
        ),
        ("entity-unique-id", "Entities have unique IDs"),
        ("has-entity-name", "Entities use has_entity_name"),
        ("runtime-data", "Runtime data uses ConfigEntry.runtime_data"),
        ("test-before-configure", "Test a connection in the config flow"),
        (
            "test-before-setup",
            "Check setup can complete during initialization",
        ),
        (
            "unique-config-entry",
            "Duplicate devices/services cannot be configured",
        ),
    ),
    "Silver": (
        ("action-exceptions", "Service actions raise exceptions on failures"),
        ("config-entry-unloading", "Config entries support unloading"),
        (
            "docs-configuration-parameters",
            "All configuration parameters are documented",
        ),
        (
            "docs-installation-parameters",
            "Installation parameters are documented",
        ),
        ("entity-unavailable", "Entities are unavailable when appropriate"),
        ("integration-owner", "Integration has an active owner"),
        (
            "log-when-unavailable",
            "Unavailable/recovery logging is rate-limited",
        ),
        ("parallel-updates", "Parallel update count is specified"),
        ("reauthentication-flow", "UI reauthentication is available"),
        ("test-coverage", "All integration modules have above 95% coverage"),
    ),
    "Gold": (
        ("devices", "Integration creates devices"),
        ("diagnostics", "Integration implements diagnostics"),
        ("discovery-update-info", "Discovery updates network information"),
        ("discovery", "Devices can be discovered"),
        ("docs-data-update", "Documentation explains how data is updated"),
        ("docs-examples", "Documentation provides automation examples"),
        ("docs-known-limitations", "Documentation lists known limitations"),
        (
            "docs-supported-devices",
            "Documentation describes supported devices",
        ),
        (
            "docs-supported-functions",
            "Documentation describes supported functions",
        ),
        ("docs-troubleshooting", "Documentation provides troubleshooting"),
        ("docs-use-cases", "Documentation describes user use cases"),
        ("dynamic-devices", "Devices can be added after setup"),
        ("entity-category", "Entities have appropriate categories"),
        ("entity-device-class", "Entities use applicable device classes"),
        (
            "entity-disabled-by-default",
            "Less popular/noisy entities are disabled",
        ),
        ("entity-translations", "Entity names are translated"),
        ("exception-translations", "Exception messages are translated"),
        ("icon-translations", "Entity icons have translations"),
        ("reconfiguration-flow", "Integration can be reconfigured in the UI"),
        (
            "repair-issues",
            "Repair issues/flows are used when intervention is needed",
        ),
        ("stale-devices", "Stale devices are removed"),
    ),
    "Platinum": (
        ("async-dependency", "External dependencies are asynchronous"),
        (
            "inject-websession",
            "HTTP dependencies accept Home Assistant web sessions",
        ),
        ("strict-typing", "Integration uses strict typing"),
    ),
}
_ALL_RULES = {rule for tier_rules in _TIERS.values() for rule, _ in tier_rules}
_STATUSES = {"done", "exempt", "todo"}
_EVIDENCE_PATH = re.compile(
    r"(?<![\w./-])(?:[\w.-]+/)*[\w.-]+\.(?:py|md|json|png|yaml|yml|toml)"
)


def _validate_rules(raw_rules: Any, repository_root: Path) -> list[str]:
    """Validate that every official checklist rule has a reasoned status."""
    if not isinstance(raw_rules, dict):
        return ["The rules field must be a mapping."]

    errors: list[str] = []
    missing = _ALL_RULES - raw_rules.keys()
    unknown = raw_rules.keys() - _ALL_RULES
    if missing:
        errors.append(f"Missing official rules: {', '.join(sorted(missing))}")
    if unknown:
        errors.append(f"Unknown rules: {', '.join(sorted(unknown))}")

    for rule, value in raw_rules.items():
        if rule not in _ALL_RULES:
            continue
        if not isinstance(value, dict):
            errors.append(f"{rule} must include status and comment.")
            continue
        if value.keys() != {"status", "comment"}:
            errors.append(
                f"{rule} must use only the official status/comment fields.")
            continue
        status = value.get("status")
        comment = value.get("comment")
        if not isinstance(status, str) or status not in _STATUSES:
            errors.append(f"{rule} has invalid status {status!r}.")
            continue
        if not isinstance(comment, str) or len(comment.strip()) < 20:
            errors.append(f"{rule} needs a meaningful comment.")
            continue
        if status == "done":
            evidence_paths = _EVIDENCE_PATH.findall(comment)
            if not evidence_paths:
                errors.append(f"{rule} is done but has no file evidence.")
            for evidence_path in evidence_paths:
                evidence = Path(evidence_path)
                if evidence.is_absolute() or ".." in evidence.parts:
                    errors.append(
                        f"{rule} has invalid evidence path: {evidence_path}")
                elif not (repository_root / evidence).is_file():
                    errors.append(
                        f"{rule} references missing evidence: {evidence_path}"
                    )
    return errors


def _render_report(raw_rules: dict[str, dict[str, str]]) -> str:
    """Render a full checklist and cumulative readiness summary."""
    lines = [
        "## Home Assistant integration quality-scale audit",
        "",
        "This is a checklist audit, not an award or certification. `DONE` and",
        "`EXEMPT` are self-assessed and must include evidence or a rationale;",
        "`TODO` means the criterion is not currently met. The listed tier is",
        "ready only when its rules and every lower tier contain no `TODO`",
        "items.",
        "",
        "| Tier | Assessed / total | Result |",
        "| --- | ---: | --- |",
    ]

    met_so_far = True
    for tier, tier_rules in _TIERS.items():
        statuses = [raw_rules[rule]["status"] for rule, _ in tier_rules]
        assessed = sum(status != "todo" for status in statuses)
        met_so_far = met_so_far and assessed == len(tier_rules)
        result = "READY (checklist only)" if met_so_far else "NOT MET"
        lines.append(f"| {tier} | {assessed} / {len(tier_rules)} | {result} |")

    for tier, tier_rules in _TIERS.items():
        lines.extend(["", f"### {tier}", ""])
        for rule, description in tier_rules:
            item = raw_rules[rule]
            status = item["status"].upper()
            lines.append(
                f"- **{status}** `{rule}` - {description}. "
                f"{item['comment']}"
            )

    return "\n".join(lines) + "\n"


def main() -> int:
    """Validate the checklist and publish its report to the CI summary."""
    repository_root = Path(__file__).resolve().parents[1]
    checklist_path = (
        repository_root
        / "custom_components"
        / "bluefire"
        / "quality_scale.yaml"
    )
    try:
        checklist = yaml.safe_load(checklist_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        print(f"Unable to read {checklist_path}: {err}", file=sys.stderr)
        return 1

    if not isinstance(checklist, dict):
        print(
            "The quality-scale file must contain a mapping.",
            file=sys.stderr,
        )
        return 1
    raw_rules = checklist.get("rules")
    errors = _validate_rules(raw_rules, repository_root)
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1

    report = _render_report(raw_rules)
    print(report, end="")
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(report)

    cumulative_ready = True
    for tier, tier_rules in _TIERS.items():
        cumulative_ready = cumulative_ready and all(
            raw_rules[rule]["status"] != "todo" for rule, _ in tier_rules
        )
        if not cumulative_ready:
            print(
                f"::warning title={tier} quality criteria not met::"
                "Review the audit summary."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
