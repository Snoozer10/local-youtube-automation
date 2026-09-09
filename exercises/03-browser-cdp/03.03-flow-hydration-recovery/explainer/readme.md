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
