# AGY receipt fingerprint corrections (additive)

Recorded: 2026-10-13T10:10:08.807Z

This annex records the reviewed R1 fingerprint mapping for current bytes. It leaves each Antigravity return and package artifact manifest byte-for-byte unchanged. A current hash is not proof of earlier execution bytes or discrepancy cause. This receipt does not accept package outputs, close substantive findings, or close master tasks.

## Counts

- 15 declarations: 12 return-document declarations and 3 stale manifest entries.
- 14 distinct package artifacts. The AGY02 frozen_inputs.json declaration appears twice (lines 48 and 115) and is one distinct artifact.
- 3 affected return documents and 3 relevant package manifests archived and hash-verified.
- AGY03 has no correction in this mapping.

## Additive binding table

| ID | Package | Source declaration | Package artifact | Original declared SHA-256 | Current SHA-256 | Bytes | Status |
|---|---|---|---|---|---|---:|---|
| R1-01 | AGY01 | docs/sessions/ANTIGRAVITY_AGY01_RETURN.md:105 | `.runtime/antigravity_offline_queue_20261012/AGY01_attempt01/RESULT.json` | `9559f939e0d1656885ca6695bfa608931215b3a4362d665b16f39385078519fc` | `1077f3a2164707ebafa38bcb9d79f5edb821eb29747fbb93efbbfdd9b6f3d972` | 24725 | return fingerprint contradicted; current bytes rebound additively |
| R1-02 | AGY01 | docs/sessions/ANTIGRAVITY_AGY01_RETURN.md:106 | `.runtime/antigravity_offline_queue_20261012/AGY01_attempt01/evidence_map.md` | `81bb45b0d5c2e36128038c92a9bf8dca34fceb15cb2ef66a4bc4d79da99e1964` | `732b51e1e356749954bf9aa369b23b706a76ac2042198391e8e7f7fdace17e25` | 9277 | return fingerprint contradicted; current bytes rebound additively |
| R1-03 | AGY02 | docs/sessions/ANTIGRAVITY_AGY02_RETURN.md:48 | `.runtime/antigravity_offline_queue_20261012/AGY02_attempt01/frozen_inputs.json` | `6fe8a82ecaa12d7c5ba2452b41fcce30e463aa29a3a9856f7ef576e271a2a4c1` | `996f46edc040cfda299678c1cdfa5be89761713e9630c9cfac65d8ebc6cc54be` | 3301 | return fingerprint contradicted; current bytes rebound additively |
| R1-04 | AGY02 | docs/sessions/ANTIGRAVITY_AGY02_RETURN.md:108 | `.runtime/antigravity_offline_queue_20261012/AGY02_attempt01/RESULT.json` | `9ff0ee3a854581f148e655ffec04dd5e887d1dfcbb7a1dfa0dfc89f5bc3a6773` | `4d7220e36bf2c444d30ed27a216bcd7f5c406f47c56763e708e79a4c663866f1` | 3944 | return fingerprint contradicted; current bytes rebound additively |
| R1-05 | AGY02 | docs/sessions/ANTIGRAVITY_AGY02_RETURN.md:109 | `.runtime/antigravity_offline_queue_20261012/AGY02_attempt01/header_report.md` | `785d03a113ec40c7ffb0070bc904576cb4053316d00465a31649d21c3fa360c7` | `b22bfe3dc64337344f370fa4e1bd4f480ee795bf46012cbd3a8570b276928776` | 8142 | return fingerprint contradicted; current bytes rebound additively |
| R1-06 | AGY02 | docs/sessions/ANTIGRAVITY_AGY02_RETURN.md:115 | `.runtime/antigravity_offline_queue_20261012/AGY02_attempt01/frozen_inputs.json` | `6fe8a82ecaa12d7c5ba2452b41fcce30e463aa29a3a9856f7ef576e271a2a4c1` | `996f46edc040cfda299678c1cdfa5be89761713e9630c9cfac65d8ebc6cc54be` | 3301 | return fingerprint contradicted; current bytes rebound additively |
| R1-07 | AGY04 | docs/sessions/ANTIGRAVITY_AGY04_RETURN.md:172 | `.runtime/antigravity_offline_queue_20261012/AGY04_attempt01/before_hashes.json` | `c37cf33d8393c3983aa41c6f3708df34273dfc0678d4cb8a0bb91823eb5ce276` | `e767d1b6fd2544f495330a93ae7c40677beb95c65fd9dcf85c2ea8000c8ff688` | 2141 | return fingerprint contradicted; current bytes rebound additively |
| R1-08 | AGY04 | docs/sessions/ANTIGRAVITY_AGY04_RETURN.md:173 | `.runtime/antigravity_offline_queue_20261012/AGY04_attempt01/after_hashes.json` | `c37cf33d8393c3983aa41c6f3708df34273dfc0678d4cb8a0bb91823eb5ce276` | `e767d1b6fd2544f495330a93ae7c40677beb95c65fd9dcf85c2ea8000c8ff688` | 2141 | return fingerprint contradicted; current bytes rebound additively |
| R1-09 | AGY04 | docs/sessions/ANTIGRAVITY_AGY04_RETURN.md:174 | `.runtime/antigravity_offline_queue_20261012/AGY04_attempt01/scope_before.json` | `b03fc290a1f054778ee9cf81912a76f254e4c34cb294d137b0d778fb8280fec7` | `8a8aa4ec4e0bb4b7f84d10d776817f6bd3514259b050cb3600fbaf091162faa7` | 10078 | return fingerprint contradicted; current bytes rebound additively |
| R1-10 | AGY04 | docs/sessions/ANTIGRAVITY_AGY04_RETURN.md:175 | `.runtime/antigravity_offline_queue_20261012/AGY04_attempt01/scope_after.json` | `ea9b9e63eefdffafebfcceef8d80c0587d60fc222402f067d025687dd7a5996b` | `514e3ff311c959cbaa6ea050d499834f3d098a725e62b5fd3fe43d1e5095a5c3` | 10078 | return fingerprint contradicted; current bytes rebound additively |
| R1-11 | AGY04 | docs/sessions/ANTIGRAVITY_AGY04_RETURN.md:176 | `.runtime/antigravity_offline_queue_20261012/AGY04_attempt01/tool_trace.jsonl` | `cb1c7df0e5999b8219c63749455eb4e414c3821034c5fae44ebae5a62f59fb5a` | `a1e96c9822fc9cbc9ca80d2943b4478e7ec1884df0b7346bad1125d5cbc78461` | 2753 | return fingerprint contradicted; current bytes rebound additively |
| R1-12 | AGY04 | docs/sessions/ANTIGRAVITY_AGY04_RETURN.md:177 | `.runtime/antigravity_offline_queue_20261012/AGY04_attempt01/artifact_hashes.json` | `79b3cb6f4370216bb9b74070be79b29cb16b9cb822eb74f3b735237890be61ee` | `89d9f3918aa6a69662979eeec7671e1d797f48a01d1258a32cc9ebceae2e252c` | 2994 | return fingerprint contradicted; current bytes rebound additively |
| R1-13 | AGY01 | .runtime/antigravity_offline_queue_20261012/AGY01_attempt01/artifact_hashes.json:4 | `.runtime/antigravity_offline_queue_20261012/AGY01_attempt01/PROGRESS.json` | `131d61586989464d3f5f5ee5427766ff7e6b5184f4338a5d5d99865e02a9ba0e` | `0561f9c2749c9863450f450bb0ddd2390527f1c90ceb1660bd3428058a8eb84c` | 4289 | stale manifest pin; current bytes rebound additively |
| R1-14 | AGY01 | .runtime/antigravity_offline_queue_20261012/AGY01_attempt01/artifact_hashes.json:36 | `.runtime/antigravity_offline_queue_20261012/AGY01_attempt01/tool_trace.jsonl` | `7611efcf2e27404894fdce683d27fa66f5fe3b3be4e66ad8cc92acd14a0c6397` | `a5daaca0a14877dabebfc08d10a7bd43401291ee853ec573908fa1de1a5b0e8b` | 1111 | stale manifest pin; current bytes rebound additively |
| R1-15 | AGY02 | .runtime/antigravity_offline_queue_20261012/AGY02_attempt01/artifact_hashes.json:2 | `.runtime/antigravity_offline_queue_20261012/AGY02_attempt01/PROGRESS.json` | `7a27e056750e1e46d506e3be51e2a2f5f45b3d6ed5c91a0bc1d2668c4e3aa312` | `0a941f04a0631b91b5f505a425f264729d9c46d39b68735c8ab30812c88eaad2` | 4752 | stale manifest pin; current bytes rebound additively |

## Preserved source records

| Original file | SHA-256 | Bytes | Archive |
|---|---|---:|---|
| `docs/sessions/ANTIGRAVITY_AGY01_RETURN.md` | `c6d8bd4fa7d92bc96301ef421245b1dd4161a89b4f48272f768bcb11417bdbeb` | 9148 | `.runtime/codex_a4_f4_packet_20261013T100625Z/r1_preimages/docs__sessions__ANTIGRAVITY_AGY01_RETURN.md` |
| `docs/sessions/ANTIGRAVITY_AGY02_RETURN.md` | `ee1d92e177971586c010ab6381bbb46b365eed224cea4091bd9378c39d93fec5` | 8889 | `.runtime/codex_a4_f4_packet_20261013T100625Z/r1_preimages/docs__sessions__ANTIGRAVITY_AGY02_RETURN.md` |
| `docs/sessions/ANTIGRAVITY_AGY04_RETURN.md` | `d2abf3f68dbb3a763e42a9ac4a2e10d35b89a94f01e36e0973cc5b38b5264f46` | 15698 | `.runtime/codex_a4_f4_packet_20261013T100625Z/r1_preimages/docs__sessions__ANTIGRAVITY_AGY04_RETURN.md` |
| `.runtime/antigravity_offline_queue_20261012/AGY01_attempt01/artifact_hashes.json` | `d05e32614e11686dc62287ff02028e9be8ca1ce5ead756d751972857bebc2f45` | 4995 | `.runtime/codex_a4_f4_packet_20261013T100625Z/r1_preimages/.runtime__antigravity_offline_queue_20261012__AGY01_attempt01__artifact_hashes.json` |
| `.runtime/antigravity_offline_queue_20261012/AGY02_attempt01/artifact_hashes.json` | `8dc1cc4c9f8d81acc35037255c37005099610fc3b8ecff1683f3690dd7ce8321` | 3629 | `.runtime/codex_a4_f4_packet_20261013T100625Z/r1_preimages/.runtime__antigravity_offline_queue_20261012__AGY02_attempt01__artifact_hashes.json` |
| `.runtime/antigravity_offline_queue_20261012/AGY04_attempt01/artifact_hashes.json` | `89d9f3918aa6a69662979eeec7671e1d797f48a01d1258a32cc9ebceae2e252c` | 2994 | `.runtime/codex_a4_f4_packet_20261013T100625Z/r1_preimages/.runtime__antigravity_offline_queue_20261012__AGY04_attempt01__artifact_hashes.json` |

Archive verification compares source-before, archived-copy, and source-after SHA-256. All three hashes must match.

## Limits and related review

- These are present-day byte bindings. They do not establish the earlier runtime state, chronology of mutable artifact updates, or root cause.
- AGY03 remains unaffected by this fingerprint correction; its separate review status is unchanged.
- AGY01 resilience evidence, AGY02 WAV implementation gaps, AGY04 proposal findings, Graphify limitations, and all branch acceptance/master-task statuses remain governed by their respective review records.

Machine receipt: [CODEX_AGY_RECEIPT_CORRECTIONS_20261013.json](CODEX_AGY_RECEIPT_CORRECTIONS_20261013.json).
