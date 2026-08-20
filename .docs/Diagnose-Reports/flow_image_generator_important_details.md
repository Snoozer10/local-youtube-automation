# `flow_image_generator.py` — Important Operational Details (Session Runbook)

**Companion to:** `flow_image_generator_technical_report.md`
**Session:** 2026-08-20 · **Status:** validated live — treat every fact below as ground truth until re-proven.

---

## 1. Environment & Topology

| Item | Value |
|---|---|
| Working dir | `C:\Users\Snoozer\Downloads\Antigravity\Youtube Automation 2\buckup\Version 4 before deepseek implementation plan\image_generation` |
| Chrome CDP | `http://127.0.0.1:9222` — the **only** browser the script drives |
| Script | `flow_image_generator.py` (3,622 lines) |
| Test dirs | `youtube_runs\test_e2e_live\`, `youtube_runs\test_run_01\` |
| Real run dir | `youtube_runs\متلازمة المحتال` (restored after dry-runs) |
| Temp (probes) | `C:\Users\Snoozer\AppData\Local\Temp\opencode\probe_*.py` |
| This runbook | `.docs\Diagnose-Reports\flow_image_generator_important_details.md` |

**MCP caveat (critical):** `chrome-devtools` and `playwright` MCP servers connect to **their own separate browser instances** — they see only `about:blank`, NOT the `:9222` Flow browser. To inspect the real Flow tabs, use CDP Python probes:

```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    for i, pg in enumerate(ctx.pages):
        print(i, pg.url, pg.title())
```

The script itself always creates **fresh pages** (`context.new_page()`), never `ctx.pages[0]` — stale page handles caused earlier repro divergence.

## 2. Browser Page Topology (observed)

- page[0] = "Application error: client-side exception" page (workspace `694ed946` crash surface)
- page[1] = healthy Flow tab
- page[2] = blank tab
- Workspace `694ed946-5d1e-4147-be83-b432fd042387` **crashes on every load**; resume machinery detects the error title and reloads → recovers. Cosmetic, expected.
- Workspace `0cde18ab-7183-43e0-8859-845b4fb23a10` loads healthy.

## 3. DOM Selector Facts (validated live on real Flow DOM)

### 3.1 Submit buttons
- **Flow uses Material Symbols, ZERO `<svg>` buttons on screen.** `button:has(svg)` will NOT match.
- Character submit = `<i class="google-symbols">arrow_forward</i> Create`.
- **Enter key is the mandatory fallback** for every submit path.

### 3.2 Workspace prompt bar (NEVER fill)
- Placeholder: `What do you want to create?` ("Agent pill" visible when focused).
- Filling it creates a **regular media image**, not a character/scene asset. Character creation inputs must be matched by their **own** placeholder/text — never a generic contenteditable fallback.

### 3.3 Character creation view
- Non-empty workspace: clicking `Characters` sidebar opens the **New Character screen directly** (header "New character"; template cards The Eccentric / The Professional / The Wildcard / The Familiar / The Wicked).
- `+ New Character` / `Create my avatar` cards exist **only on empty-workspace gallery state**.
- `Create my avatar` = **webcam modal — never click**.
- Prompt input candidates (verification-gated):
  - `textarea[placeholder*='Describe your character' i]`
  - `input[placeholder*='Describe your character' i]`
  - `div[contenteditable='true']` whose `inner_text` contains `describe your character` (probe-validated path — the prompt label text lives inside the contenteditable)
- Workspace bar text (`What do you want to create?`) can never satisfy the check → injection into feed is impossible.

### 3.4 Character Editor (`/character/<id>`)
- Editor **auto-mounts on submit**; measured ≤1–3s live.
- Mount detectors: URL `/character/<id>` OR `button:has-text('Done')` OR `textarea[placeholder*='Describe how your character acts' i]`.
- **NEVER re-click submit** during the 25–130s render-blocked navigation — re-submit spam corrupts the session. Patient waits only.
- Rename: click `Untitled Character` → `input[value*='Untitled' i], input[placeholder*='Character' i], h1[contenteditable='true']`.
- Info bio: acts-family textarea (`Describe how your character acts`).
- Portrait wait: poll image render to 100% + `Create Body` button **enabled** (`disabled`/`aria-disabled` check).
- `Done` = `button:has-text('Done'), button:has-text('تم'), button:has-text('حفظ')`.

### 3.5 Body triptych popup
- Clicking `Create Body` opens a **floating card** with placeholder `Describe body and outfit....`.
- Input is a `div[contenteditable='true']` (or custom textbox) — **NOT** a placeholder `<textarea>`.
- Candidate cascade (in order): `div[contenteditable='true']` **`.last`** → `get_by_placeholder(re.compile(r"(body|outfit|صف)", re.I))` → body/outfit textareas → `[role='textbox']` last → `textarea` last.
- Fill: `fill()`; on failure `el.innerText = ...` + dispatch `input` event.
- Submit: Material Symbol arrow inside popup container, **Enter fallback** (svg selectors fail).
- 3-view verification: `[role='progressbar']`/`.animate-spin`/percent → initiation ≤15s; triptych confirmed via center-canvas `naturalWidth > 300` until 180s.

## 4. Hydration & Timing Rules

- `wait_for_flow_app_ready(page)` — sidebar + content visible, then a **3s stability window** before any click. Clicks during React hydration are **silently swallowed**.
- Required after every `goto` / reload / resume (workspace 694ed946 especially).
- `wait_for_flow_generation_handshake` (2-phase): indicator present **≥5s** (mount debounce, kills False-Green) → poll unmount + image painted.
- `wait_for_flow_generation_idle`: popup/editor renders, 90s budget.

## 5. Extraction Facts (full-res, no CORS)

- Flow `<img>` src is **relative**: `/fx/api/trpc/media.getMediaUrlRedirect?...` — the old `http(s)://` filter silently missed it.
- Canvas `toDataURL()` throws `SecurityError` on Cloud CDN assets (tainted canvas) — **dead code, removed**.
- Working tier chain (`extract_high_res_image`):
  1. `data:image` → base64 decode
  2. `http(s)://` or `/` → `urljoin(page.url, src)` + `page.request.get()` → **Network Stream** (browser session auth, no canvas)
  3. `blob:` → in-page `fetch(img.src)` → FileReader dataURL
  4. Screenshot fallback → atomic temp-file + Pillow `verify()` + `os.replace`
- Validated output: **1376×768 native** (≥1280×720 gate).

## 6. Teardown & Process Safety

- `safe_failover_teardown()`: `context.close()` → `browser.close()` → sleep 1s → `rotate_profile_index()` → `kill_cdp_chrome()` → sleep 2s. **CDP handles detached before OS-level kill** — prevents `TargetClosedError` + orphaned `:9222` binding.
- PowerShell output buffering: always launch `python -u -X utf8`; `log()` helper flushes every line.
- `QSV_LOOKAHEAD=0` (compile stage) — unrelated here but repo-wide invariant.

## 7. Failure Modes & Pivots (do NOT repeat)

| Failure | Root cause | Pivot |
|---|---|---|
| Portrait became regular image | Click swallowed → typed into `What do you want to create?` bar | Verification-gated input match (placeholder/text) + card-click transition loop ≤3 attempts |
| `+ New Character` click no-op | Hydration swallowed click; card absent on non-empty workspaces | Verify `Describe your character` view after click; retry; label regex `^(\+?\s*New Character|\+?\s*شخصية جديدة)$` + parent-card + plus-card fallback |
| Gallery re-open loop navigated away from editor | Old code clicked `Characters` sidebar after submit | Linear flow: submit → wait editor mount (URL/Done/acts) |
| Body popup not found | mat-dialog/role=dialog selectors; real input = contenteditable floating card | `.last` contenteditable cascade + placeholder regex |
| False-Green render complete | Single mount check | 2-phase handshake (5s debounce + unmount poll) |
| `button:has(svg)` submit fail | Material Symbols, zero svg buttons | arrow_forward selector + Enter fallback |
| 542×303 screenshots | Canvas CORS + relative-URL filter bug | Network Stream via `urljoin` + `page.request.get()` |
| TargetClosedError on failover | `taskkill` raced open CDP sockets | Graceful detach before kill |
| Delayed logs | Python block buffering | `python -u` + `flush=True` log helper |
| `Create my avatar` trap | Webcam modal | Never click; only `+ New Character` label |

## 8. Verification Anchors (evidence of baseline)

- e2e run 03:38–03:40: both chars full chain (card → input → mount → rename → info → portrait → **body triptych rendered** → Done), 4 scenes created+renamed, manifest `flow_assets_profile_2.json` saved, `00_04.png` extracted 1376×768.
- `py_compile` clean · `ruff format` clean · `ruff check` = **11 pre-existing** errors only (B007/F841/C414).
- **Zero new debug snapshots** in final runs — all 4 existing (`char_editor_fail`, `char_nav_fail`, 02:42–03:19) predate fixes.
- Real folder `youtube_runs\متلازمة المحتال` restored from temp (14 items).

## 9. Open Items (known-cosmetic, optional)

1. `'Add to Prompt' button not found in asset dialog` during @CHARACTER/@SCENE summon — assets still resolve; renders succeed. Fix if summoning stops working.
2. Workspace `694ed946` Application-error on load — resume reload recovers; cosmetic.
3. Console `ERR_NAME_NOT_RESOLVED` + `unload not allowed` — harmless.
4. `flow_image_generator.py` changes uncommitted — commit only on user request.