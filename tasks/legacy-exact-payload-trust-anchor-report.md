# Legacy Exact-Payload Trust-Anchor Regression Isolation Report
**Task E04 (Issue #91): Isolate Legacy Exact-Payload Trust-Anchor Regression**
**Campaign Context**: Issue #78 (Architecture Renewal Campaign)
**Task Branch**: `test/e04-isolate-trust-anchor-regression`
**Base Commit**: `1e6b8bf5a6a35d54c628206808208869a47760d1` (`origin/master`)
**Date**: 2026-11-09

---

## 1. Executive Summary

This report documents the resolution of the confirmed test gap recorded under inventory item **E04** in `tasks/REMAINING_WORK.md:86`:
> *"Isolate the legacy exact-payload trust-anchor regression: make the target inactive and remove competing anchors so the test proves the intended one alone. Preserve positive/negative timestamp/tamper cases."*

In `tests/unit/test_profile_activation.py:299-332`, the parametrized test `test_legacy_active_revision_bootstraps_digest_receipt_from_valid_anchor` tests whether unreceipted legacy profile revisions can bootstrap their immutable digest receipt (`profile.sha256`) upon reactivation. However, in the baseline test, the target revision remained active (`manager.active_pointer_file` pointed to `original.revision`). Consequently, during the `exact_payload` parameterization, both trust anchors (`pointer_matches` and `existing_digest == compute_profile_digest(profile_dict)`) were simultaneously satisfied, creating a false-pass vulnerability where exact-payload bootstrapping was never verified in isolation.

The test has been updated to activate an intermediate distinct revision (`Achird`), making `original` strictly inactive prior to candidate publication. The isolation was validated empirically via mutation analysis, demonstrating that disabling exact-payload validation causes `exact_payload` to fail closed while `active_pointer` passes.

---

## 2. Technical Analysis & Problem Diagnostic

In `src/youtube_automation/production/profile_activation.py:343-348`, legacy profiles lacking a `profile.sha256` receipt are permitted to bootstrap that receipt under two strict, mutually independent conditions:

```python
_ensure_profile_digest_receipt(
    rev_dir,
    existing_bytes,
    may_bootstrap=existing_digest == compute_profile_digest(profile_dict)
    or pointer_matches,
)
```

The two allowed trust anchors are:
1. **Exact-Payload Anchor** (`existing_digest == compute_profile_digest(profile_dict)`): The candidate profile submitted for activation is byte-for-byte identical in semantic content to the published unreceipted profile.
2. **Active-Pointer Anchor** (`pointer_matches == True`): The revision is currently pointed to by `manager.active_pointer_file` with a matching digest.

### The Baseline Flaw

In the baseline implementation of `test_legacy_active_revision_bootstraps_digest_receipt_from_valid_anchor`:

```python
manager = ProfileActivationManager(tmp_path / "channel_dna")
manager.publish_and_activate(original)
revision_file = manager.revisions_dir / original.revision / "profile.json"
published_bytes = revision_file.read_bytes()
receipt_file = revision_file.with_name("profile.sha256")
receipt_file.unlink()

result = manager.publish_and_activate(candidate)
```

1. For `bootstrap == "active_pointer"`: `candidate` was created with a differing timestamp (`2026-11-01T00:00:01Z` vs `00:00:00Z`), making `existing_digest == compute_profile_digest(...)` `False`. Because `original` was active, `pointer_matches` was `True`. This correctly tested `active_pointer` alone.
2. For `bootstrap == "exact_payload"`: `candidate` was set to `original`. However, `original` was still the active revision in `manager.active_pointer_file`. Therefore, `pointer_matches` was also `True`. If the exact-payload condition `existing_digest == compute_profile_digest(...)` were completely deleted or broken, the test would continue to pass because `pointer_matches` masked the regression.

---

## 3. Resolution & Isolation Architecture

To isolate the exact-payload anchor:
1. `original` is published and activated, establishing the unreceipted revision on disk.
2. `profile.sha256` is unlinked.
3. For `bootstrap == "exact_payload"`, an independent competing profile (`competing = derive_production_profile(study, {"voice": "Achird"})`) is published and activated.
4. The test explicitly asserts:
   ```python
   assert manager.get_active_revision() == competing.revision
   assert manager.get_active_revision() != original.revision
   ```
5. `original` is now strictly **inactive**. When `manager.publish_and_activate(candidate)` is called:
   - `pointer_matches` is `False` (active pointer points to `competing.revision`).
   - The only path allowing `may_bootstrap=True` is `existing_digest == compute_profile_digest(profile_dict)`.
6. For `bootstrap == "active_pointer"`, `original` remains active, but `candidate` has a differing `created_at` timestamp, ensuring `existing_digest == compute_profile_digest(...)` is `False`.
7. Both parameterizations are now strictly mutually exclusive: each tests exactly one trust anchor with zero competing fallback.

---

## 4. Empirical Mutation Verification

To verify the test's sensitivity to regressions in the trust anchor logic, the implementation in `src/youtube_automation/production/profile_activation.py:346` was temporarily mutated:
```python
# Temporary mutation: disable exact_payload bootstrap
may_bootstrap=False or pointer_matches
```

Execution against mutated code yielded:
- `test_legacy_active_revision_bootstraps_digest_receipt_from_valid_anchor[exact_payload]`: **FAILED** with `ValueError: Inactive legacy profile has no published profile digest receipt`
- `test_legacy_active_revision_bootstraps_digest_receipt_from_valid_anchor[active_pointer]`: **PASSED**

This confirms that:
- `exact_payload` cannot pass via `pointer_matches`.
- Any regression in exact-payload validation immediately triggers test failure.
- The mutation was cleanly reverted prior to commit.

---

## 5. File Lineage & Hash Verification

Preimages were archived into private ignored storage (`.runtime/e04_trust_anchor_20261109/`):

| File | SHA256 Preimage | Modified SHA256 | Line Ending |
|---|---|---|---|
| `tests/unit/test_profile_activation.py` | `aad066dbc0d89f31e525901e88f463026a445b1421b1d4870ba6040c506bdac6` | `f97d8cc1fb95b61769ff671239a8d4766353062a8a68c3cb5833884e2da269dd` | Pure LF (`\n`) |

---

## 6. Verification Checklist

- [x] `tests/unit/test_profile_activation.py`: 15 passed in 5.80s.
- [x] Mutation sensitivity: proven via empirical failure of `exact_payload` when anchor disabled.
- [x] Linter: `ruff check tests/unit/test_profile_activation.py` passed with 0 errors.
- [x] Documentation integrity: `python tools/check_readme.py` passed (7 documents checked).
- [x] Whitespace & formatting: `git diff --check` clean (0 warnings).
- [x] Negative & tamper coverage: preserved existing tests for missing/tampered receipts and tampered timestamps.
