# Experiments overview

| experiment | status | title |
|---|---|---|
| EXP01 | success | Minimal ZMK shield for the ADS1220 TrackPoint, built on GitHub Actions |
| EXP02 | success | Full-path ADS1220 logging: handshake to readings and errors |
| EXP03 | success | ADS1220 no-read root cause: CS must not be tied to GND |
| EXP04 | failed | Circle-motion capture: is the raw X/Y signal good enough for pointer motion? |
| EXP05 | failed | IDAC always-on: is the capture a poll-rate settling artefact? |
| EXP06 | failed | Gain 16: does the neutral come into the input window? |
| EXP07 | success | Gain ladder: how big is the neutral offset? (found the malformed-sample fault) |
| EXP08 | success | Read-path root cause: the (H,H,L) duplication was a 1-byte-short RDATA read - fixed with a 4-byte read |
| EXP09 | inProg | Node sweep: is the -4.4M common-mode the AIN2 mid-bias? |
