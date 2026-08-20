# `flow_image_generator.py` — Attempts, Failures & Success Log (Full Session Ledger)

**Companion to:** `flow_image_generator_technical_report.md` (post-mortem) · `flow_image_generator_important_details.md` (runbook)
**Session:** 2026-08-20 (02:42 → 03:40 UTC local, live validation)
**Outcome:** 100% end-to-end automated generation — baseline locked.

---

## Phase 0 — Starting Condition (broken)

| # | Symptom | Root cause (later proven) |
|---|---|---|
| F0.1 | Runtime `IndentationError` / mis-scoped logic in `setup_flow_characters_and_scenes` | 221-line block drifted out of alignment across prior surgical edits |
| F0.2 | Index errors / wrong data during render loop | Raw 7-element positional tuples; variable shadowing (`frame` reused); tuple slicing |
| F0.3 | `TypeError: locator: expected a string, got tuple` | Selector lists passed as tuples to `page.locator()` — needs one comma-joined string |
| F0.4 | Unauditable exception swallowing | Bare `except: pass` everywhere, no classification |
| F0.5 | `SecurityError` on extraction | Canvas `toDataURL()` on Cloud CDN assets = tainted canvas, forbidden by spec |
| F0.6 | Extraction silently downscaled (542×303) | Relative `/fx/api/trpc/media.getMediaUrlRedirect?...` src URLs rejected by `http(s)://`-only filter |
| F0.7 | `TargetClosedError` / orphaned `:9222` on failover | `taskkill /F` raced open CDP sockets |
| F0.8 | Stale debug output | Python block buffering when piped to `Tee-Object` |

---

## Phase 1 — Architectural Refactor (all landed, all successful)

| # | Attempt | Result |
|---|---|---|
| S1.1 | `python -m py_compile` as first gate after every edit | ✅ Syntax regressions caught instantly thereafter |
| S1.2 | `StoryboardFrame` frozen dataclass replaces 7-tuple | ✅ Named fields; immutability; index/slicing bug class eliminated |
| S1.3 | `FlowSelectors` / `GeminiSelectors` registries; comma-joined `PROGRESS_INDICATORS` string | ✅ `locator()` tuple TypeError gone; selectors single-sourced |
| S1.4 | 3-tier exception taxonomy (Tier 1 DOM probes / Tier 2 OS-file / Tier 3 extraction-teardown logging), inline comments | ✅ Audit-able swallowing; no silent sites left |
| S1.5 | `log()` with `flush=True` + `python -u` launch | ✅ Real-time trace output |
| S1.6 | `safe_failover_teardown()` — context.close → browser.close → sleep → `kill_cdp_chrome()` | ✅ Failover without `TargetClosedError` |

---

## Phase 2 — Full-Resolution Extraction (fail → fix → pass)

| # | Attempt | Outcome |
|---|---|---|
| A2.1 | In-memory canvas `toDataURL()` fallback | ❌ `SecurityError` — Cloud CDN taints canvas; **dead code, removed** |
| A2.2 | Network branch filtered `src.startswith(("http://","https://"))` | ❌ Silent miss — real src is **relative** (`/fx/api/trpc/...`) |
| A2.3 | `urljoin(page.url, src)` + `page.request.get()` → Network Stream | ✅ 1376×768 native; browser-session auth; no canvas/CORS |
| A2.4 | `blob:` in-page fetch → FileReader dataURL (Tier 2B) | ✅ Same-origin, no CORS; guard for blob sources |
| A2.5 | Atomic screenshot (temp + Pillow `verify()` + `os.replace`) | ✅ Tier 3 fallback; never writes truncated partials |

**Possibilities evaluated & rejected:** fetching via raw `requests` (no session auth → 401 on redirect chain); CDP `Page.captureScreenshot` with clip (still DOM-res; kept only as last resort).

---

## Phase 3 — Browser Session / CDP Stability

| # | Attempt | Outcome |
|---|---|---|
| A3.1 | OS-level `taskkill /F` on failover | ❌ Raced open sockets → `TargetClosedError` |
| A3.2 | Graceful CDP detach BEFORE kill (`safe_failover_teardown`) + `rotate_profile_index()` | ✅ Clean port handoff, next run connects |
| A3.3 | `python -u` + flushed `log()` | ✅ Live streaming into `run_trace_live.log` |

---

## Phase 4 — Character Creation State Machine (the long war)

### 4.1 Attempt sequence (chronological)

| # | Attempt | Evidence | Outcome |
|---|---|---|---|
| A4.1 | Submit → acceptance-loop polling (re-check gallery after submit) | — | ❌ Rejected `/character/<id>` editor URLs as "not accepted"; **8s re-submit spam broke 25–130s render-blocked navigation** |
| A4.2 | Patient waits + editor-URL = accepted | — | ✅ Editor mount confirmed ≤1–3s via URL/Done/acts textarea |
| A4.3 | Old "re-open Characters gallery" click after submit (to "return") | User diagnosis #1 | ❌ Flow auto-transitions into editor; the click navigated **away** from active editor → switched to **linear** submit→wait-mount flow |
| A4.4 | 45s editor-mount timeout | — | ❌ Too tight; bumped to 120s + URL check |
| A4.5 | Click `+ New Character` card, then generic contenteditable input | User diagnosis #2 (screenshots: 3-card gallery) | ❌ On **empty** workspace gallery, `+ New Character` (left) + `Create my avatar` (right); `Create my avatar` = **webcam modal trap**; generic contenteditable matched the **workspace bar** → portrait became a regular image |
| A4.6 | `probe_gallery_dom.py` | DOM dump | ✅ Discovery: **non-empty** workspace `Characters` tab opens the **templates screen directly** (header "New character", template cards The Eccentric/The Professional/The Wildcard/The Familiar/The Wicked, contenteditable `Describe your character…`, `arrow_forward Create`). `+ New Character` cards = empty-state only |
| A4.7 | `probe_chain_validate.py` | Live probe | ✅ **Confirmed chain:** fill contenteditable + Material Symbol `arrow_forward` submit → editor mounted in **1s** → `/character/83d71f2a-7293-41f5-b2fa-af03fab25700`, `Done` + acts textarea visible |
| A4.8 | Sidebar nav single click then input fill | User diagnosis #3 (smoking-gun screenshot) | ❌ Nav click **swallowed during hydration** → stayed on All Media → typed into workspace bar → portrait as regular media image |
| A4.9 | Strict nav loop (3 attempts, verify `/characters` URL or New-character DOM) + strict input (`textarea/input[placeholder*='Describe your character' i]` only) | User-provided fix | ✅ Nav + input correct; run 03:24 reached submit + editor wait — **user aborted** to hand the exact card-click spec |
| A4.10 | `wait_for_flow_app_ready` (sidebar+content + **3s stability window** after goto/reload) | — | ✅ Kills hydration-swallow class of bugs |
| A4.11 | **Final (user spec):** Step 3 `card_attempt` loop 1–3 — check `Describe your character` input visible → else click `get_by_text(r'^(\+?\s*New Character|\+?\s*شخصية جديدة)$', re.I)` + parent-card fallback + plus-card fallback → **verify transition**; input = placeholder **or** contenteditable-with-label-text; NEVER workspace bar | Applied | ✅ Run 03:30+: `Transitioned to 'Describe your character' view!` attempt 1/3, both workspaces |

**Possibilities evaluated & rejected:**
- `div[contenteditable='true']:not([placeholder*='What do you want' i])` generic fallback → **rejected** (matched workspace bar, made portrait-as-image bug)
- `Create my avatar` card → **rejected** (webcam modal)
- `button:has(svg)` submit → **rejected** (Flow uses Material Symbols; zero `<svg>` buttons; Enter mandatory fallback)

### 4.2 Editor steps (all successful in final run)

Rename (`Untitled Character` → inline input family) → Character Info (acts textarea) → portrait render 100% + `Create Body` enabled → Create Body → Done (`Done`/`تم`/`حفظ`).

---

## Phase 5 — Body Triptych Generation

| # | Attempt | Outcome |
|---|---|---|
| A5.1 | `[placeholder*='outfit' i], [placeholder*='body' i]` + mat-dialog/`[role='dialog']`/cdk-overlay-pane selectors | ❌ Run 03:30–03:31: "⚠️ Could not locate Body prompt popup box" ×4 (both chars × both workspaces) — Flow is not Material-Angular; popup input is a **`div[contenteditable='true']` floating card** (`Describe body and outfit....`) |
| A5.2 | **Final (user spec):** candidate cascade — `div[contenteditable='true']` `.last` → `get_by_placeholder(r'(body\|outfit\|صف)')` → body/outfit textareas → `[role='textbox']` last → `textarea` last; `fill()` with `innerText`+`input`-event fallback; submit = popup arrow (Material Symbol; svg fails) with **Enter fallback**; monitor via `[role='progressbar']`/spinner/percent + triptych `naturalWidth > 300` | ✅ Run 03:38–03:40: `Inserting Body Triptych prompt into popup bar...` → `Character Body Triptych 100% rendered and confirmed in DOM!` ×2 chars |

---

## Phase 6 — Scene Pre-Flight & Frame Rendering

| # | Attempt | Outcome |
|---|---|---|
| A6.1 | Scene render on feed → rename newest card via 3-dots menu | ✅ 4/4 scenes generated + renamed (both workspaces) |
| A6.2 | Post-Done editor guard: still on `/character/<id>` → navigate to root before scenes | ✅ Fired once in run 03:31/03:40, recovered clean |
| A6.3 | Summon `@CHARACTER_*` / `@SCENE_*` into prompt | ⚠️ `'Add to Prompt' button not found in asset dialog` — assets still resolve; **open cosmetic item** |
| A6.4 | Handshake monitor + `extract_high_res_image` | ✅ `Saved (Network Stream): 00_04.png` |

---

## Phase 7 — Final Validation (03:38–03:40)

| Check | Result |
|---|---|
| `test_e2e_live` (workspace 694ed946, crash-on-load) | ✅ Pre-flight cache hit; frame extracted 1376×768 |
| `test_run_01` (workspace 0cde18ab) | ✅ Both chars FULL chain incl. body triptych; 4 scenes; manifest saved; frames skipped (exist) |
| `py_compile` / `ruff format` | ✅ Clean |
| `ruff check` | ✅ 11 pre-existing only (B007/F841/C414), zero new |
| Debug snapshots | ✅ Zero new (all 4 = 02:42–03:19 pre-fix) |
| Exit | ✅ `All topics processed successfully. Exiting.` |
| Real folder `متلازمة المحتال` | ✅ Restored to `youtube_runs\` |

---

## Open Possibilities / Next Candidates

| Item | Status |
|---|---|
| Fix `'Add to Prompt'` dialog button during @asset summon | Non-blocking; investigate only if summoning regresses |
| Silence workspace 694ed946 Application-error reload noise | Cosmetic; resume machinery already handles |
| Real full run on `youtube_runs\متلازمة المحتال` | Ready; expect >30min (2+ chars, 4 scenes, N frames) |
| Commit `flow_image_generator.py` changes | User-initiated only |
| Migrate remaining 11 pre-existing lint errors | Optional cleanup, unrelated to flow |

---

## Ledger Rules (codified this session)

1. Browser-automation edit → `py_compile` → `ruff check` → `ruff format` before any browser work.
2. Probe-first for unknown DOM (`probe_*.py` in Temp); never guess selectors from memory.
3. Verification-gated interactions only (placeholder/text checks); generic selectors only as explicitly ordered fallbacks.
4. Never re-click during render-blocked navigation; patient waits with URL/DOM checks.
5. Extract via network stream (no canvas); screenshot only as final tier.
6. Detach CDP before OS-level kill.
7. Unbuffered logging always (`python -u`, `flush=True`).