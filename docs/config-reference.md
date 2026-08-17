# Configuration Reference — Al-Daheeh Engine

Runtime configuration for the YouTube Video Automation Pipeline (Al-Daheeh Engine).
This document covers the flags read from `.env` and the account-failover / notification
subsystem. Pipeline-stage configs (`video_config.txt`, `transcribe_config.txt`,
`daheeh_config.json`) are documented in their own files.

---

## Reading `.env` Values

All pipeline scripts read configuration through `utils.get_config_value()` with an
inline default — no `os.environ` accesses exist outside this helper. The helper
accepts the flag name and a fallback default:

```python
get_config_value("SWITCH_ACCOUNTS_ENABLED", "false")
```

Boolean flags are parsed with the unified, fail-closed idiom:

```python
get_config_value("FLAG", "false").strip().lower() in ("true", "1", "yes")
```

Anything that is not exactly `true`, `1`, or `yes` (case-insensitive) is treated as
**false** — including missing values, empty strings, and typos. There is no way to
accidentally enable a flag.

---

## Account Switching

| Flag | Default | Readers |
| :--- | :------ | :------ |
| `SWITCH_ACCOUNTS_ENABLED` | `false` | `generate_voice.py` L895, `flow_image_generator.py` L678, `script_image_generator.py` L649, `generate_thumbnail.py` L455, `refine_script.py` L324 |

When `true`, the per-stage scripts rotate among the browser profiles listed in
`CHROME_USER_DATA_DIRS` (defined in `utils.py`) instead of always using the default
profile. Rotation is monotonic: each script invocation advances the profile index by
one (`utils.rotate_profile_index`, L154) and maps it through
`map_profile_index` (L70):

- index `1` → `Default`
- index `N` → `Profile N - 1`

`SWITCH_ACCOUNTS_ENABLED` is the **only** switch for rotation. All five readers use
the same fail-closed parsing, so the flag behaves identically at every pipeline
stage.

---

## Failover & Retry

| Flag | Default | Meaning |
| :--- | :------ | :------ |
| `FAILOVER_RETRY_LIMIT` | `3` / `4` (per reader, see below) | Max profile-failover retries before a stage gives up |
| `ACTIVE_PROFILE_INDEX` | `1` | Index of the currently active profile; advanced by `rotate_profile_index` |

`FAILOVER_RETRY_LIMIT` is read by three scripts, with per-script inline defaults:

- `generate_voice.py` L1267 — default `3`
- `generate_thumbnail.py` L453 — default `4`
- `refine_script.py` L322 — default `4`

`flow_image_generator.py` (L1276) and `automate_all.py` do **not** read the flag —
they use a hardcoded 3-attempt failover loop.

The failover loop wraps the CDP browser session:

1. Launch browser on the current profile.
2. On connect/operation failure, advance `ACTIVE_PROFILE_INDEX` via
   `rotate_profile_index` (`utils.py` L154).
3. Retry until the retry limit is exhausted, then raise / fall through.

`rotate_profile_index` clamps at the profile list length, so a failed rotation never
wraps around to a profile that just failed. `map_profile_index` (`utils.py` L70)
maps the numeric index to a profile name (1 → `Default`, N → `Profile N - 1`).

---

## Telegram Notifications

| Flag | Default | Meaning |
| :--- | :------ | :------ |
| `TELEGRAM_BOT_TOKEN` | — | Bot token used by `utils.send_telegram_notification` (L167, reads at L169) |
| `TELEGRAM_CHAT_ID` | — | Recipient chat ID (read at `utils.py` L170) |
| `TELEGRAM_NOTIFY_PER_STEP` | `false` | Per-step progress alerts from the pipeline runner |

Notification sources:

- `generate_thumbnail.py` (L564) sends alerts on **both** success and failure.
- `generate_voice.py` sends **no** direct alerts — voice failures surface through
  the runner's failure alerts.
- `run_agency.py` (L303) is the only reader of `TELEGRAM_NOTIFY_PER_STEP`: when
  `true`, it emits an alert after every completed pipeline step; when `false`
  (default), alerts fire only on failures.

`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are required for any notification to
send; if either is missing, `send_telegram_notification` degrades to a no-op.

---

## Quick Reference

| Flag | Default | Purpose |
| :--- | :------ | :------ |
| `SWITCH_ACCOUNTS_ENABLED` | `false` | Rotate browser profiles per stage |
| `FAILOVER_RETRY_LIMIT` | `3` / `4` | Max failover retries (per-script defaults) |
| `ACTIVE_PROFILE_INDEX` | `1` | Current profile index (advanced on failover) |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | — | Telegram recipient chat ID |
| `TELEGRAM_NOTIFY_PER_STEP` | `false` | Per-step progress notifications |

`.env.example` mirrors these defaults and is the canonical template for new runs.