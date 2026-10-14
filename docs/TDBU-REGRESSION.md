# TDBU 0.4.1 regression evidence

Scope: rail command coordination and position reporting. This is a source-level,
transport-mocked regression suite, not a Home Assistant frontend or hardware test.
The installed Home Assistant source/version and preset YAML have not been retrieved;
live parity remains unverified because Home Assistant was unreachable.

The reported fixture has both raw rail positions at 35, with the top physically
mostly lowered and the bottom immediately underneath it. The old top entity reports
65 and the bottom can retain a stale estimated 0 despite the raw reading of 35.
The intended full-open destination is both rails raised, represented by 100/100.

Run `python3 -m unittest discover -s tests -v`. The suite loads production constants,
coordinator methods and cover methods with minimal framework substitutes. The hub
transport is a fake that yields during every POST to expose concurrent scheduling.
No live hub requests occur. Motion registration substitutes omit HA background tasks;
notification polling, real retry timing and firmware behavior are not certified.

14 test cases pass on the candidate, including:

- Full-open from 35/35, in both rail orders, sequentially and concurrently.
- Concurrent independent moves preserve both destinations.
- Every tested guarded full-open payload obeys bottom <= middle.
- Companion movement is recorded for motion tracking and verification.
- Lowering the top moves an obstructing bottom to a compatible height.
- Positive minimum gap is maintained at travel endpoints.
- Unknown companion position prevents incomplete TDBU commands.
- Disabling the guard preserves the companion position.
- Single-rail payloads retain their original shape.
- Failed POSTs register no phantom targets.
- Retry payloads preserve the latest companion target.
- A retry superseded while waiting for the shade lock sends nothing.
- Completed estimates display reported height; new estimates start at measurement.

The same 14-case suite against cf6d5a6 (the command-race-only fix, before direction,
pair planning and display changes) reports 7 failures. This validates that the suite
catches the unresolved preset and position-display defects rather than merely passing
both implementations.

Hardware verification still required: install the candidate, confirm both raw rail
positions increase as they rise, execute full-open from the lowered privacy position,
and confirm physical arrival and final reported values. Review numeric scene targets
when upgrading because the top position inversion has changed.
