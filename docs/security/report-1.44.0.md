# Security report, tapiOca 1.44.0

Run 2026-10-24.
A local run, at commit cc5fea6924fef6f4e6846eb09e468b36d6f33f4c.
Python 3.11.15, pytest 9.1.1.

| Area | Severity | Passed | Failed |
| --- | --- | --- | --- |
| The census: every way out, program and write declared (A.1, DEP-03, DEP-04) | High | 15 | 0 |
| Every route from every vantage point (AZ-01 to AZ-03, AUTH-01, AUTH-02) | Critical | 226 | 0 |
| Sign-in tokens: ended at once, never in an address or a log, kinds kept apart (AUTH-06, 06b, 07) | Critical | 9 | 0 |
| Outbound requests by provenance (SSRF-01 to SSRF-08) | Critical | 54 | 0 |
| Paths on every route with a parameter (INJ-01) | Critical | 37 | 0 |
| The four scripted chains (CHAIN-01 to CHAIN-04) | Critical | 12 | 0 |
| The live harness (attack_check) | Critical | 812 | 0 |

Checks in all: 1165 (the corpus last recorded 1139).

Tracked exceptions (Medium):
- none

