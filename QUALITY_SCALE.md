# Home Assistant integration quality scale

This project tracks the Home Assistant Bronze, Silver, Gold, and Platinum
integration-quality criteria. It is not currently claiming certification at any
tier. The integration is preparation-only: the vendor BLE protocol and live
telemetry receiver are not implemented, so several runtime criteria remain
unmet.

## Checklist and verification

The complete rule assessment is maintained in
[`custom_components/bluefire/quality_scale.yaml`](custom_components/bluefire/quality_scale.yaml).
Each official rule is marked `done`, `exempt`, or `todo`, with a rationale;
completed rules cite repository evidence. The CI quality-scale audit checks
that every known rule is assessed, rejects unknown rules and invalid statuses,
and verifies evidence paths. Its Actions summary lists each rule and whether
the cumulative tier checklist is ready.

`READY (checklist only)` means every rule in that tier and all lower tiers has
been assessed as done or exempt. It is a self-assessment, not a Home Assistant
award. A successful audit only confirms the checklist is complete and evidence
references exist; it does not certify the integration or validate runtime
behavior.

CI also runs the hardware-free unittest suite, PEP 8 checks, HACS validation,
and Home Assistant's hassfest validation. The checklist and its audit do not
replace those checks or manual testing in Home Assistant.

## Current limitations

- BlueFire BLE authentication, notification framing, and live reception are not
  implemented. The checklist therefore does not claim that vehicle telemetry
  works or that all device-related criteria are met.
- The quality checklist is an assessment of current behavior, not a promise that
  every criterion is complete. `todo` entries are intentionally visible and
  should only change when implementation, tests, or documentation provide
  evidence for the criterion.
- Update this assessment and the audit's official rule catalog when Home
  Assistant changes its
  [integration quality-scale checklist](https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/).
