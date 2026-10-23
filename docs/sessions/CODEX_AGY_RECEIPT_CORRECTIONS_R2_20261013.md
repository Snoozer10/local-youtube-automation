# AGY receipt corrections — R2 additive annex

Recorded:2026-10-13T17:54:30.917Z

F01–F10 review findings accepted by user. This annex applies only F01 and F04 using the R1 additive pattern;R1 and all original AGY05–08 artifacts remain byte-identical. Current bytes do not establish earlier execution identity or cure original log closure order. B2 raw-derived offline validation remains verified. This annex does not close B5,fidelity,polish or any production gate.

| ID | Finding | Original declaration | Verified current bytes | Status |
|---|---|---|---|---|
|R2-01|F01|AGY06 OUTPUT_MANIFEST.json:logs/seal.stdout.log;0B;SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`|1228B;SHA `59aaeec7a1da047ec764b1a11e1856459baf2199e7a5c970d8f317a55540082c`|Original manifest entry contradicted;closed current bytes rebound additively|
|R2-02|F04|AGY08 RETURN.md external source PDF;45713B|350203B;SHA `ea76bc3b19a8110bcdca360a5673d2c727573b0ec3ab7a608174c231512e33ce` matches declared digest|Size corrected only;original digest supported|

## Preservation and verification

Four affected declaration/artifact sources byte-archived with exclusive create and before/after SHA checks;all106 original package files pinned for final preservation check. Evidence:`.runtime/codex_r2_agy09_preparation_20261013T175324Z/BASELINE.json`;machine companion:CODEX_AGY_RECEIPT_CORRECTIONS_R2_20261013.json. Final receipt/SEAL under the same runtime folder.

No helper rerun,Audacity,network,provider,source edit or Git mutation. Sealer log provenance remains limited;future executions must have parent-close stdout/stderr before payload hashing. This coordinator annex is a new independent receipt and preserves the original failed manifest.
