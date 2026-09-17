# Explainer: SPA Hydration Recovery, CDK Overlay Interception & Card-Spawn Handshake

## 1. SPA Client-Side Hydration vs `domcontentloaded`

When `page.goto(url, wait_until='domcontentloaded')` resolves, the browser has parsed
the initial HTML and fired `DOMContentLoaded`. However, Google Flow is a React SPA:
JavaScript must run, fetch async data, and mount components before the
`div[contenteditable='true']` prompt bar exists in the DOM.

Typical timeline after reload:
- `t=0ms` — `domcontentloaded` fires (HTML parsed)
- `t=2,000–5,000ms` — React hydration completes
- `t=5,000–10,000ms` — `contenteditable` prompt bar visible and interactive

**Rule:** Never check for a SPA component immediately after navigation. Always poll with a
timeout long enough to cover hydration (15s covers the p99 case).

## 2. `page.wait_for_timeout()` vs `time.sleep()`

Playwright's Python sync API is built on greenlets. The underlying CDP WebSocket transport
requires the greenlet scheduler to pump incoming frames. `time.sleep()` blocks the OS
thread, preventing CDP frames (DOM mutations, console events, network responses) from
being processed. `page.wait_for_timeout(ms)` yields control back to the Playwright
scheduler so the transport stays alive.

**Rule:** Never use `time.sleep()` inside Playwright polling loops. Use `page.wait_for_timeout(ms)`.

## 3. Angular Material CDK Overlay Architecture

Google Flow uses Angular Material components. Angular's CDK (Component Dev Kit) renders
dropdown menus, tooltips, and dialogs by **portaling** them to a single root element:

```html
<body>
  <app-root>...</app-root>

  <!-- Angular CDK injects overlays here — NOT inside the trigger button -->
  <div class="cdk-overlay-container">
    <div class="cdk-overlay-backdrop settings-menu-backdrop"></div>
    <div class="cdk-overlay-pane">
      <div role="menu">
        <button>Nano Banana Pro</button>
        <button>Nano Banana 2</button>
        <button>Nano Banana 2 Lite</button>
      </div>
    </div>
  </div>
</body>
```

### Why This Breaks Naive Automation

If you try `page.locator("button.mat-mdc-menu-trigger").locator("[role='menuitem']")`, you
get **zero results** — the menu items are not children of the trigger button. They live at
the document root inside `div.cdk-overlay-container`.

### Stale Backdrop Interception

When a settings popup is open and you navigate away or another action fires, Angular may
leave a `cdk-overlay-backdrop` element in place. This backdrop intercepts all pointer
events over the page, causing all subsequent `.click()` calls to silently fail.

**Detection and clearance:**
```python
# Detect stale backdrop
backdrop = page.locator(".cdk-overlay-backdrop")
if backdrop.is_visible():
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
```

### Correct CDK Menu Interaction Pattern

```python
# 1. Click the settings trigger (the toolbar chip — NOT the model button directly)
page.locator("[aria-label='Settings trigger']").click(force=True)
page.wait_for_timeout(600)

# 2. Click the model family selector INSIDE the settings popup
model_btn = page.locator("button[aria-label='Select model family']").first
model_btn.click(force=True)
page.wait_for_timeout(500)

# 3. Find menu options in the CDK overlay container at the root (NOT inside model_btn)
model_opt = page.locator(
    "div.cdk-overlay-container [role='menuitem'], div.cdk-overlay-container button"
).filter(has_text="Nano Banana 2 Lite").first
model_opt.click(force=True)
```

## 4. React SyntheticEvent-Safe Text Injection

Google Flow's prompt bar uses React with Lexical/ProseMirror for rich text editing.
Direct DOM value assignment (`element.value = 'text'`) does not fire React's
`beforeinput` / `input` synthetic events. The Generate button stays disabled.

Correct approach:
1. `input_locator.click()` — focus
2. `page.keyboard.press('Control+a')` — select all
3. `page.keyboard.press('Backspace')` — clear
4. `page.keyboard.insert_text(text)` — native paste that fires all React events

## 5. Card-Spawn Handshake vs Global DOM Polling

### The Problem with Checking `progressbar` Immediately

After pressing Enter/clicking Generate, there is a 2–20 second delay before Google Flow
creates a new generation card in the workspace. During this time:
- No `[role='progressbar']` is visible (generation hasn't started rendering yet)
- No `%` text appears
- The prompt input box may still contain the submitted text

Old approach (fragile): Check for progressbar immediately, assume stall if not found.  
**This caused false re-triggers** and double-submissions.

### The Card-Spawn Handshake

Before submission, record the current card count. After submission, poll until the count
increases (a new card appeared) OR a progressbar becomes visible:

```python
# BEFORE submission
pre_card_count = page.locator(
    "div[data-card-index], .generation-card, [role='article']"
).count()

# Submit prompt...
page.keyboard.press("Enter")
page.wait_for_timeout(2000)

# AFTER submission: wait up to 20s for new card
card_spawned = False
for _ in range(20):
    curr_count = page.locator(
        "div[data-card-index], .generation-card, [role='article']"
    ).count()
    if curr_count > pre_card_count:
        card_spawned = True
        break
    if page.locator("[role='progressbar']").is_visible():
        card_spawned = True
        break
    page.wait_for_timeout(1000)

if not card_spawned:
    # Safe re-trigger: check input still contains the text before pressing Enter again
    box_text = input_box.evaluate("el => el.value || el.innerText || ''").strip()
    if box_text and "what do you want" not in box_text.lower():
        page.keyboard.press("Enter")
```

## 6. Quota / Rate-Limit Error Detection

Google Flow renders quota errors as text directly in the workspace card:

> *"Failed — You've reached your usage limit. Please try again later. You have not been charged for this generation."*

This text does **not** match generic error selectors like `[role='alert']`. It must be
caught with `page.get_by_text(re.compile(...))` inside the generation watchdog loop:

```python
error_locators = page.get_by_text(re.compile(
    r"(unusual activity|couldn't generate|failed to generate|"
    r"policy violation|reached your usage limit|you have not been charged)",
    re.IGNORECASE,
))
```

**Why this matters:** Without this pattern, the watchdog silently spins for 120s waiting
for a progressbar that will never appear, then triggers a full reload-and-retry cycle.
With it, the error is detected within one poll cycle (≤1s), and account rotation begins
immediately.

## 7. Two-Tier Timeout Strategy

| Timer | Duration | Trigger | Action |
| :--- | :--- | :--- | :--- |
| Stall timeout | 120s | No `active_card` loading activity | Reload page, re-inject prompt |
| Hard ceiling | 360s | Absolute from prompt submit | Dump diagnostics, rotate account |

## 8. Scoped Generation Card Watching

A Google Flow workspace accumulates historical generation cards (card 1, card 2, ...,
card N). Checking `.animate-pulse` globally detects shimmer from *any* card, including
old already-rendered ones that re-animate on scroll. Scoping the watchdog to the *last*
card container eliminates these false positives:

```python
active_card = page.locator(
    "div[data-card-index]:last-child, .generation-card:last-child, [role='article']:last-child"
).first

# Inside watchdog loop — scoped to active_card only
is_loading = active_card.locator(
    "[role='progressbar'], .animate-pulse, [class*='shimmer'], [class*='skeleton']"
).first.is_visible()
```

## 9. Windows DWM Occlusion Defense

On Windows, the Desktop Window Manager (DWM) can occlude minimized or background Chrome
windows, causing Chromium to throttle JavaScript timers and reduce rendering priority.
This manifests as `setTimeout` callbacks firing late, slowing SPA hydration.

**Defense:** Launch Chrome with these flags to disable native window occlusion:

```python
chrome_flags = [
    "--disable-features=CalculateNativeWinOcclusion",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
]
```

## 10. Dual Diagnostic Artifact Dumper

On any stall, save both:
- `error_frame_XXX_attY_TIMESTAMP.png` — raster screenshot
- `error_frame_XXX_attY_TIMESTAMP.html` — full DOM snapshot via `page.content()`

The HTML snapshot reveals hidden `z-index` overlays, detached nodes, and CDK backdrop
elements that are invisible in screenshots. This is the primary debugging tool for
Angular Material / React SPA automation failures.

## 11. Reverse-Chronological Grid Feed Prepending & Coordinate Sorting

Google Flow workspaces prepend newly generated cards and tiles to the top of the feed (lowest `y` coordinate).
When sorting candidate images by bounding box coordinates:
- Never sort with `candidates[-1]` (which selects stale historical tiles at the bottom of the feed).
- Always sort ascending by `(y, x)` and select `candidates[0]` (the top-most, newest prepended tile).
- Account for Google Flow's 2-column grid layout where two variants are generated side-by-side per prompt.

## 12. Quadruple-Lock Handshake & Dual-Mode "Add to Prompt"

To eliminate stale scrape collisions across multi-step generation batches:
1. **Lock 1**: Pre-submit card count snapshot and candidate image source registry (`pre_image_srcs`).
2. **Lock 2**: Continuous modal, consent banner, and quota interceptor before any pointer action.
3. **Lock 3**: Card-spawn handshake with 45s exponential backoff and progressbar detection.
4. **Lock 4**: 15-frame rolling SHA-256 hash collision ledger (`RollingSha256Ledger`) that rejects duplicate renders and triggers hard-reload recovery.
5. **Dual-Mode Engine**: Mode A (Master Setup) with full 2D vector style DNA and strict text quarantine; Mode B (Surgical Delta) with L.A.D. formula `<25 words` and native CDK "Add to Prompt" chip attachment.

## 13. Character Drawer Virtualization & Presets Summoning Protocol

Google Flow allows registering persistent Character assets (`الشخصيات` / `Characters`) to maintain facial and artistic identity across prompts. Automating character chip attachment requires handling two SPA intricacies:

1. **Angular CDK Virtualized Asset Grids**:
   The drawer list (`div.cdk-overlay-container`) only mounts DOM nodes for currently visible character cards. If an asset (e.g. `CHARACTER_HOST_MAIN`) lies above or below the active scroll window, querying its selector returns 0 elements.
   *Protocol:* When an asset selector fails, pump bidirectional mouse wheel scrolls (`overlay.hover()`, `page.mouse.wheel(0, -600)`, `page.mouse.wheel(0, 600)`) to force Angular CDK to mount all registered items before failing.

2. **Single-Click Direct Attach vs Detail Confirmation**:
   In Google Flow, clicking an asset button (`button.asset-item`) can immediately attach the chip to the prompt bar and dismiss the overlay. If a secondary detail view opens, it displays an explicit "Add to prompt" button (`الإضافة إلى الطلب`).
   *Protocol:* Record prompt bar chip counts (`button.chip-container`) before interaction. If the chip count increases immediately after clicking `char_btn`, treat the summon as successful. If the detail view opens, click `الإضافة إلى الطلب`, dismiss the overlay via `Escape`, and assert final chip count growth.

## 14. Fatal Quota Saturation vs Transient Card Errors & Account Rotation

Google Flow enforces daily generation burst limits on free-tier accounts. When reached, the UI displays:
> *"لقد بلغت الحدّ الأقصى للاستخدام. يُرجى إعادة المحاولة لاحقًا."* (*"You've reached your usage limit. Please try again later."*)

### Transient vs Fatal Error Scoping
- **Transient Card Errors**: An individual generation card can fail (`تعذَّر إكمال المعالجة`, `failed to generate`). This is scoped to that specific card and can be recovered via a retry.
- **Fatal Account Quota Exhaustion**: Appears globally or on every submitted prompt.

### The Cascading Failure Anti-Pattern
If the runner does not distinguish fatal quota errors from transient glitches, it will catch the error, mark the frame as failed, and iterate to the next frame. It repeats this across all remaining pending frames (3 reload attempts × N frames), burning minutes of unnecessary network traffic and polluting disk artifacts.

### The Correct Rotation Protocol
1. Implement `is_fatal_flow_quota_error(text)` detecting strings like `الحدّ الأقصى للاستخدام`, `reached your usage limit`, `quota exceeded`.
2. When detected, immediately halt the batch runner without attempting remaining frames.
3. Automatically rotate Chrome profiles (`rotate_profile_index()`, e.g., Profile 1 → Profile 2 → Profile 3) on the CDP loopback port (`127.0.0.1:9222`) and resume seamlessly.

## 15. Conversational Agent Interception & UI Mode Desynchronization

Google Flow provides an experimental "Agent" mode toggle (`button:has-text('Agent')`) in the prompt bar. When toggled on or if a conversational side panel is active:
1. Submitting text prompts triggers a conversational video generation approval modal:
   > *"Would you like me to kick off this 1 video generation, costing 15 credits? Approve / Reject"*
2. The agent attempts to generate video rather than discrete Nano Banana 2 16:9 images.
3. Pointer events and prompt inputs are intercepted by the modal.

### Dismissal & Mode Reset Protocol
The automated harness must enforce pure image generation before every prompt:
1. Click "Reject" on any conversational confirmation prompt.
2. Close any open agent side drawer using its close button.
3. Check whether the Agent toggle pill is active (`aria-pressed='true'` or highlighted background style). If active, click it to toggle Agent mode OFF, restoring direct image diffusion.

## 16. Chrome CDP Subdomain-Strict Tab Resolution

When connecting to Chrome over CDP (`127.0.0.1:9222`), multiple tabs may be open within the authenticated profile (e.g., Google AI Studio, Gemini, YouTube Studio, and Google Flow).

### The Broad Substring Anti-Pattern
Checking `if "google.com" in page.url` or loose matching easily binds the automation harness to the wrong tab (such as `gemini.google.com` or `aistudio.google.com`), causing subsequent DOM queries for Flow components to time out.

### The Strict Match Protocol
Always filter open pages strictly by subdomain or exact path:
```python
flow_pages = [
    p for p in context.pages
    if "flow.google" in p.url or "/flow" in p.url
]
```
If no active tab matches, navigate the first available tab explicitly to `https://flow.google.com/`.

## 17. Transient Card Spawn Timeout & Self-Healing Retry Handshake

During prolonged batch generation runs (e.g. 50–200 continuous frames), Google Flow backend latency or transient WebSocket queue stalls can occasionally prevent a new generation card from spawning within the initial 45s handshake window.

### Anti-Pattern: Immediate Hard Crash on Single-Attempt Queue Lags
Treating a single 45s card-spawn timeout as a fatal error halts the pipeline or causes unnecessary account rotation even when account quota remains plentiful and the profile is completely healthy.

### Self-Healing Multi-Attempt Protocol
1. Trap card spawn timeout exceptions gracefully within the frame generation loop.
2. Log an informative warning (`⚠️ Card spawn timed out after 45s on Attempt 1. Reloading...`).
3. Execute a complete SPA reload (`page.reload(wait_until="domcontentloaded")`).
4. Wait for full SPA hydration via `wait_for_flow_input_box(page)`.
5. Dismiss blocking modals or agent side-drawers via `dismiss_blocking_agent_and_modals(page)`.
6. Re-inject the prompt on Attempt 2.
*In production, this pattern routinely achieves 100% recovery on Attempt 2 (validated on Frame 200 of Chunk 4), preserving batch continuity without human intervention.*

## 18. Render Watchdog Stalls vs Card-Spawn Latency

A robust generation harness must distinguish two distinct failure stages during diffusion execution:

1. **Card-Spawn Latency (Pre-Render)**:
   - *Phase*: Occurs within the first 0–45s immediately after submitting a prompt.
   - *Symptom*: No generation card container or article DOM node is spawned.
   - *Root Cause*: Gateway request queueing, transient network drops, or unmounted CDK components.

2. **Render Watchdog Stall (Mid-Render)**:
   - *Phase*: Occurs after the card container has mounted in the workspace feed.
   - *Symptom*: The card displays an indefinite shimmer or progress indicator without producing a completed `img[src]` within the 120s stall ceiling.
   - *Root Cause*: Backend model worker timeouts, safety review latency, or GPU partition failure.
   - *Recovery Protocol*: When the 120s stall ceiling triggers, the runner logs `⚠️ Render timed out on Attempt 1. Reloading...`, forces a clean page reload, re-verifies hydration, and re-injects the prompt for Attempt 2. This achieved 100% automated recovery on **Frame 207 of Chunk 5**, producing a clean 913 KB asset without interruption.

## 19. Cross-Account Character Library Scoping & Mode A Graceful Fallback

In multi-account rotating architectures (e.g. cycling through Chrome Profiles 1–4 when free-tier quotas expire), character preset libraries introduce an important account-scoping challenge:

1. **Account-Scoped Asset Isolation**:
   Google Flow stores user-created Character presets (`CHARACTER_HOST_MAIN`, `CHARACTER_CLERK_BUREAUCRAT`) strictly within individual Google user accounts and projects. When the runner rotates to a fresh profile, the new account's Characters tab reports `No assets found.`.

2. **Localization Invariant in Ingredient Triggers**:
   The prompt bar ingredient button uses `aria-label="Add ingredients to the prompt box"` in English and `aria-label="إضافة المكوّنات"` in Arabic. Automation selectors must match both languages:
   ```python
   add_btn = page.locator(
       "button[aria-label*='Add ingredient' i], button[aria-label*='إضافة المكوّنات' i], button[aria-label*='Add asset' i], button:has-text('add')"
   ).last
   ```

3. **Autonomous Mode A Fallback Engine**:
   When `summon_character_chip()` returns `False` (`FAILED/SKIPPED`), the dual-mode prompt builder must **never** crash or stall. Instead, it gracefully reverts to **Mode A (Master Setup)** where `expand_asset_tokens()` injects the explicit 2D cartoon visual DNA:
   > *"Al-Daheeh Egyptian cartoon educational host, dark curly hair, black round glasses, animated expressive comedic facial expression, 2D graphic vector animation style, clean white background #FFFFFF..."*
   This guarantees that character visual identity and style invariants remain intact across all frames, even prior to explicit character asset creation in the target profile.

## 20. Comparison Studio Viewer Baseline Path Resolution & Multi-Chunk Scaffolding

When reviewing visual prompt iterations side-by-side, comparison viewers must maintain strict spatial separation between baseline and candidate frames:

1. **The Post-Consolidation Path Collision Trap**:
   When compiling final video outputs, the production engine consolidates newly enhanced frames into `generated_images/` while archiving original unenhanced assets into `generated_images_baseline/`. If comparison viewers hardcode baseline image URLs to `../generated_images/{fname}`, both the baseline panel and candidate panel resolve to the identical consolidated file on disk, preventing visual audit.

2. **Authoritative Baseline Priority**:
   The viewer metadata builder (`build_frame_records`) must inspect directory layout at runtime:
   ```python
   if os.path.exists(os.path.join(run_dir, "generated_images_baseline")):
       baseline_dir_name = "generated_images_baseline"
   else:
       baseline_dir_name = "generated_images"
   ```
   All relative paths must be derived dynamically via `os.path.relpath(target_path, html_dir)` to guarantee valid image links regardless of whether the viewer is hosted in a chunk subfolder or the project root.

3. **Multi-Chunk Paged Scaffolding & Initial Landing**:
   In chunked rollout workflows (e.g. 50-frame slices), local viewers only host assets for their designated slice. The viewer must:
   - Provide chunk-specific filters (`Chunk 1: Frames 1–50`, `Chunk 2: Frames 51–100`, etc.).
   - Support seamless fallback to `socratic_master_frames/` for frames outside the local chunk.
   - Automatically initialize rendering at the first available local frame (`initIdx = frames.findIndex(f => f.in_local_dir && f.canary_exists)`) so opening a chunk viewer immediately lands on relevant frames rather than empty preceding slots.

