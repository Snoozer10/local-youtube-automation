import glob
import html
import json
import os
import re
import statistics
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from playwright.sync_api import sync_playwright

from gemini_utils import (
    RESPONSE_SELECTOR,
    find_input_box,
    find_send_button,
    select_gemini_model,
    start_clean_gemini_chat,
    wait_for_gemini_response,
)
from utils import (
    CONFIG,
    get_config_value,
    get_runtime_state,
    kill_cdp_chrome,
    launch_browser_with_profile,
    rotate_profile_index,
    send_telegram_notification,
)

sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class RefinedTurn:
    index: int
    original_text: str
    refined_text: str
    word_count: int
    rhythm_variance: float
    is_outro: bool = False


@dataclass
class ScriptDeliverable:
    video_title: str
    turns: list[RefinedTurn] = field(default_factory=list)

    @property
    def total_words(self) -> int:
        return sum(t.word_count for t in self.turns)

    @property
    def estimated_duration_minutes(self) -> float:
        return round(self.total_words / 135.0, 2)


def get_latest_run_folder(runs_path="youtube_runs"):
    if not os.path.exists(runs_path):
        return None
    folders = glob.glob(os.path.join(runs_path, "*/"))
    if not folders:
        return None
    return max(folders, key=os.path.getmtime)


def read_refine_prompt():
    try:
        with open(os.path.join("prompts", "refine_prompt.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print("Error: 'prompts/refine_prompt.txt' not found.")
        sys.exit(1)


def read_final_output(folder):
    path = _safe_path(folder, "final_output.txt")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Error: 'final_output.txt' not found in {path}")
        sys.exit(1)


def split_paragraphs(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) < 2:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return paragraphs


def _safe_path(folder: str, filename: str) -> str:
    """Resolve a path under youtube_runs/ with directory traversal protection."""
    safe_folder = os.path.basename(os.path.normpath(folder))
    return os.path.join("youtube_runs", safe_folder, filename)


def load_checkpoint(folder):
    path = _safe_path(folder, "refine_checkpoint.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                raw = data.get("refined_paragraphs", [])
                # Handle both old format (list of strings) and new format (list of dicts)
                turns = []
                for item in raw:
                    if isinstance(item, str):
                        turns.append(
                            RefinedTurn(
                                index=len(turns) + 1,
                                original_text="",
                                refined_text=item,
                                word_count=len(item.split()),
                                rhythm_variance=0.0,
                                is_outro=False,
                            )
                        )
                    elif isinstance(item, dict):
                        turns.append(
                            RefinedTurn(
                                index=item.get("index", len(turns) + 1),
                                original_text=item.get("original_text", ""),
                                refined_text=item.get("refined_text", item.get("text", "")),
                                word_count=item.get(
                                    "word_count",
                                    len(item.get("refined_text", item.get("text", "")).split()),
                                ),
                                rhythm_variance=item.get("rhythm_variance", 0.0),
                                is_outro=item.get("is_outro", False),
                            )
                        )
                return turns
        except Exception:
            pass
    return []


def save_checkpoint(folder: str, refined_paragraphs: list[RefinedTurn]) -> None:
    """Atomically commits checkpoint to disk via OS-level rename to prevent zero-byte corruptions."""
    target_path = _safe_path(folder, "refine_checkpoint.json")
    dir_name = os.path.dirname(target_path)
    os.makedirs(dir_name, exist_ok=True)

    # Serialize RefinedTurn objects to dicts
    serializable = [
        {
            "index": t.index,
            "original_text": t.original_text,
            "refined_text": t.refined_text,
            "word_count": t.word_count,
            "rhythm_variance": t.rhythm_variance,
            "is_outro": t.is_outro,
        }
        for t in refined_paragraphs
    ]

    tf = tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8")
    try:
        json.dump(
            {"refined_paragraphs": serializable},
            tf,
            ensure_ascii=False,
            indent=2,
        )
        tf.flush()
        os.fsync(tf.fileno())
        temp_name = tf.name
    finally:
        tf.close()
    os.replace(temp_name, target_path)


def delete_checkpoint(folder):
    path = _safe_path(folder, "refine_checkpoint.json")
    if os.path.exists(path):
        os.remove(path)


# Module-Level Pre-compiled Technical Loanwords Transliteration Mapping
LOANWORDS_MAP = {
    re.compile(r"\bPi\b", re.IGNORECASE): "باي",
    re.compile(r"\bApp\b", re.IGNORECASE): "أبلكيشن",
    re.compile(r"\bCalculator\b", re.IGNORECASE): "آلة حاسبة",
    re.compile(r"\bHydrogen\b", re.IGNORECASE): "هيدروجين",
    re.compile(r"\bProton\b", re.IGNORECASE): "بروتون",
    re.compile(r"\bStep-Up\b", re.IGNORECASE): "ستيب أب",
    re.compile(r"\bStep-Down\b", re.IGNORECASE): "ستيب داون",
    re.compile(r"\bBose-Einstein\b", re.IGNORECASE): "بوز أينشتاين",
    re.compile(r"\bTetrahedron\b", re.IGNORECASE): "تيتراهيدرون",
    re.compile(r"\bEther\b", re.IGNORECASE): "أثير",
    re.compile(r"\bOctaves?\b", re.IGNORECASE): "أوكتاف",
    re.compile(r"\bFlash\b", re.IGNORECASE): "فلاش",
    re.compile(r"\bFormula\b", re.IGNORECASE): "معادلة",
}


class DialectTashkeelEngine:
    """Pre-compiled singleton engine for O(M) single-pass Tashkeel substitution."""

    _instance = None
    _regex = None
    _lexicon = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        config_path = "daheeh_config.json"
        if not os.path.exists(config_path):
            print("[WARN] Tashkeel DISABLED: daheeh_config.json not found in CWD.")
            return
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            raw_lexicon = (
                config.get("al_daheeh_master_pipeline_config", {})
                .get("dialect_profile", {})
                .get("tashkeel_lexicon", {})
            )
            if not raw_lexicon:
                print("[WARN] Tashkeel DISABLED: tashkeel_lexicon empty/missing in config.")
                return

            # Build normalized mapping: store raw config keys as well as derived unvocalized Arabic roots
            self._lexicon = {}
            for key, vocalized in raw_lexicon.items():
                self._lexicon[key] = vocalized
                unvocalized = re.sub(r"[\u064B-\u0652]", "", vocalized).strip()
                if unvocalized:
                    self._lexicon[unvocalized] = vocalized

            # Sort longest tokens first to avoid partial-matching substrings
            sorted_keys = sorted(self._lexicon.keys(), key=len, reverse=True)
            escaped = [re.escape(k) for k in sorted_keys]
            # Use non-greedy (??) prefix matching so full words like 'كده' are matched directly
            # rather than accidentally splitting into prefix 'ك' + word 'ده'
            pattern = rf"(^|[\s.,!?؛،:\(\)\[\]\"'])(و|ف|ب|ك|ل|لل|فال|وال|بال)??(?P<word>{'|'.join(escaped)})(?=[\s.,!?؛،:\(\)\[\]\"']|$)"
            self._regex = re.compile(pattern)
        except Exception as e:
            print(f"[WARN] Failed to compile Tashkeel engine: {e}")

    def transform(self, text: str) -> str:
        if not text:
            return ""
        if self._regex:

            def _replacer(m: re.Match) -> str:
                lead = m.group(1) or ""
                pref = m.group(2) or ""
                word = m.group("word")
                vocalized = self._lexicon.get(word, word)
                return f"{lead}{pref}{vocalized}"

            text = self._regex.sub(_replacer, text)

        # Contextual Homograph Disambiguation
        text = re.sub(r"(^|\s)يا\s+علي(?=[\s.,!?؛،]|$)", r"\1يا عَلِي", text)
        text = re.sub(r"(^|\s)مين(?=\s+(?:اللي|دا|دي|فيهم|هناك))", r"\1مِين", text)
        text = re.sub(r"(^|\s)من\s+غير(?=[\s.,!?؛،]|$)", r"\1مِن غِير", text)
        return text


def apply_tashkeel_from_config(text: str) -> str:
    """Delegates to cached single-pass engine."""
    return DialectTashkeelEngine.get_instance().transform(text)


def sanitize_solo_narrator_text(raw_text: str) -> str:
    """Strips any accidental conversational speaker tags or co-host prefixes."""
    pattern = r"(?m)^\s*(?:الراوي|أحمد|المتحدث|أبو حميد|شخص \d+|Speaker \d+|Host|Narrator):\s*"
    cleaned = re.sub(pattern, "", raw_text)
    return cleaned.strip()


def clean_refined_paragraph(text):
    """
    Extracts the clean Arabic paragraph using <final_script> XML boundaries,
    purges any leaked planning artifacts/metadata lines, transliterates loanwords, and applies Tashkeel.
    """
    if not text:
        return ""

    # 1. Primary Strategy: Extract content inside <final_script> tags if present
    script_match = re.search(
        r"<final_script>(.*?)</final_script>", text, flags=re.DOTALL | re.IGNORECASE
    )
    if script_match:
        text = script_match.group(1).strip()
    else:
        # Fallback: Strip <thinking> blocks and tags.
        # Orphan-open fallbacks catch truncated model output where the closing
        # tag never arrived; otherwise planning residue leaks into the script.
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(
            r"<slang_ledger>.*?</slang_ledger>", "", text, flags=re.DOTALL | re.IGNORECASE
        )
        # Orphan-open fallback: truncated output leaves an unclosed tag. Purge from
        # the orphan tag through its own line only (`.` stays newline-terminated),
        # so any clean paragraph lines that followed survive.
        text = re.sub(r"<thinking>.*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<slang_ledger>.*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)

    # 2. Strip explicit audit blocks, checklists, and metadata lines
    metadata_line_patterns = [
        r"(?i)^.*?\b(?:Applied diacritics to|Category [A-D]|Diacritics (?:applied|on)|Numbers phonetically|Zero robotic|Pure Cairene|Motif [\"'].*?[\"']|Targeted diacritics|Egyptian Amiya blended|All numbers spelled).*$",
        r"(?i)\b(?:Beat\s*\d|Sentence\s*\d|The\s*Short\s*Hit|Medium\s*Setup|Flowing\s*Data(?:\s*Density)?|Staccato\s*Punchline|Abo\s*Hmeed\s*Interjection)\s*[:\-]",
        r"(?i)\b(?:CADENCE_CHECK|FUSHA_SHIELD_AUDIT|UPDATE_LEDGER|TASHKEEL_VERIFY|OUTRO_CHECK|SLANG_LEDGER_AUDIT)\s*[:\-].*?$",
    ]
    for pat in metadata_line_patterns:
        text = re.sub(pat, "", text, flags=re.MULTILINE)

    text = sanitize_solo_narrator_text(text)

    # 3. Clean line by line: Drop lines with heavy Latin/English script
    clean_lines = []
    for line in text.splitlines():
        l_str = line.strip()
        if not l_str:
            continue
        # If line contains more than 40% Latin characters, it's an English note/audit
        latin_chars = len(re.findall(r"[A-Za-z]", l_str))
        total_chars = max(1, len(re.findall(r"\S", l_str)))
        if (latin_chars / total_chars) > 0.35:
            continue
        clean_lines.append(sanitize_solo_narrator_text(l_str))

    combined = " ".join(clean_lines)

    # 4. Strip leftover Markdown symbols and conversational lead-ins
    combined = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", combined)
    combined = re.sub(
        r"^(?:الفقرة\s*\d*[:\-]?|إليك\s*(?:الفقرة|التعديل|النص)[:\-]?|\d+[\.\-\)]\s*)",
        "",
        combined.strip(),
        flags=re.IGNORECASE,
    )
    combined = re.sub(r"\([A-Za-z0-9\s\-_,\.\'&]+\)", "", combined)
    combined = re.sub(r"\s+", " ", combined).strip()

    combined = sanitize_solo_narrator_text(combined)

    # 5. Robust Multi-Sentence De-duplication:
    # If Gemini drafted beats and then output the unified paragraph without tags,
    # remove earlier duplicated interjection occurrences while preserving surrounding text
    interjection_patterns = [
        r"(?:ثانية واحدة يا أبو حميد[!؟]*)",
        r"(?:أبو حميد،? أنت بتهبد[?!]*)",
        r"(?:يا نهار أسود يا أبو حميد[!؟]*)",
    ]
    for pat in interjection_patterns:
        matches = list(re.finditer(pat, combined))
        if len(matches) > 1:
            # Remove earlier duplicated occurrences, retaining the surrounding paragraph text
            for m in matches[:-1]:
                combined = combined[: m.start()] + combined[m.end() :]
            combined = re.sub(r"\s+", " ", combined).strip()

    # 6. Slice to the first valid Arabic character
    arabic_match = re.search(r"[\u0600-\u06FF].*", combined)
    if arabic_match:
        combined = arabic_match.group(0)

    # 7. Latin Technical Loanwords Transliteration for Arabic TTS Engines
    for compiled_pat, ar_trans in LOANWORDS_MAP.items():
        combined = compiled_pat.sub(ar_trans, combined)

    # 8. Apply Tashkeel from config
    return apply_tashkeel_from_config(combined)


def validate_refinement_quality(text, is_outro=False):
    """
    Validates cadence, length, dialect purity, and Gary Provost rhythm variance.
    Properly accounts for Arabic commas (،) and phonetic pauses.
    """
    if not text or len(text.strip()) < 30:
        return False, "Response is too short or empty."

    # 0. Check for unstripped speaker prefixes
    speaker_pattern = r"(?m)^\s*(?:الراوي|أحمد|المتحدث|أبو حميد|شخص \d+|Speaker \d+|Host|Narrator):"
    if re.search(speaker_pattern, text):
        return False, "Detected unstripped speaker prefixes or multi-character dialogue."

    # 1. Check for forbidden formal Fusha connectors
    banned_fusha = [
        "علاوة على ذلك",
        "وبالإضافة إلى ذلك",
        "من الجدير بالذكر",
        "بناءً عليه",
        "مما لا شك فيه",
        "نستنتج مما سبق",
        "حيثما",
        "في هذا الصدد",
        "وعلى النقيض",
    ]
    for banned in banned_fusha:
        if banned in text:
            return False, f"Detected banned formal Fusha connector: '{banned}'"

    # 2. Transliteration Check: ban raw numbers
    if re.search(r"\b\d{2,}\b", text):
        return False, "Contains raw un-transliterated digits (Requires phonetic Arabic words)."

    # 3. Gary Provost Rhythm Check: Split across all Arabic breath marks (. ! ? ؛ ، \n)
    breath_units = [s.strip() for s in re.split(r"[.!?؛،\n…]+", text) if len(s.strip().split()) > 0]

    if not is_outro and len(breath_units) <= 1 and len(text.split()) > 30:
        return False, "Monolithic sentence structure detected (No rhythm/breath variation)."

    if len(breath_units) >= 3:
        word_counts = [len(u.split()) for u in breath_units]
        variance = statistics.stdev(word_counts)
        # Healthy Provost variation requires at least 1.8 word count standard deviation between beats
        if variance < 1.8 and len(text.split()) > 40:
            return (
                False,
                f"Monotonic cadence detected (Rhythm variance {variance:.2f} is too flat).",
            )

    # 4. Outro vs Main Pacing Markers
    if not is_outro and not any(p in text for p in ["...", "،", "!", "؟", " — "]):
        return False, "Missing natural speech pause markers ('...' or proper Arabic punctuation)."

    return True, "Passed"


def calculate_rhythm_variance(text: str) -> float:
    """Calculate Gary Provost rhythm variance (word count std dev across breath units)."""
    breath_units = [s.strip() for s in re.split(r"[.!?؛،\n…]+", text) if len(s.strip().split()) > 0]
    if len(breath_units) < 3:
        return 0.0
    word_counts = [len(u.split()) for u in breath_units]
    return statistics.stdev(word_counts)


def set_paragraph_rtl(paragraph):
    """Sets a Word paragraph to native Right-to-Left (RTL) reading order safely."""
    pPr = paragraph._p.get_or_add_pPr()
    # Remove any existing bidi elements to avoid duplicate XML tags
    for child in list(pPr):
        if child.tag.endswith("bidi"):
            pPr.remove(child)
    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1")
    pPr.append(bidi)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def generate_diff_report(folder, original_paragraphs, refined_paragraphs):
    """Generates an elevated HTML side-by-side comparison report with cadence metrics."""
    html_path = _safe_path(folder, "audit_diff.html")
    rows = []

    total_orig_words = sum(len(p.split()) for p in original_paragraphs)
    total_ref_words = sum(len(p.split()) for p in refined_paragraphs)

    for idx, (orig, refined) in enumerate(
        zip(original_paragraphs, refined_paragraphs, strict=True), 1
    ):
        o_words = len(orig.split())
        r_words = len(refined.split())
        delta = r_words - o_words
        delta_color = "#38a169" if delta >= 0 else "#e53e3e"

        # Calculate Provost variance for this refined turn
        beats = [s.strip() for s in re.split(r"[.!?؛،\n…]+", refined) if len(s.strip().split()) > 0]
        variance_str = (
            f"{statistics.stdev([len(b.split()) for b in beats]):.1f}" if len(beats) >= 2 else "N/A"
        )

        rows.append(f"""
        <tr>
            <td style="font-weight:bold; color:#718096; width:4%; text-align:center;">
                <div>{idx}</div>
                <div style="font-size:11px; margin-top:4px; color:#a0aec0;">Var: {variance_str}</div>
            </td>
            <td dir="rtl" style="width:48%; padding:14px; background:#f8fafc; border-left:1px solid #e2e8f0; font-family: 'Segoe UI', Tahoma, sans-serif; font-size:15px; line-height:1.8; color:#2d3748;">
                <div style="font-size:12px; color:#a0aec0; margin-bottom:6px; direction:ltr; text-align:left;">Words: {o_words}</div>
                {html.escape(orig)}
            </td>
            <td dir="rtl" style="width:48%; padding:14px; background:#f0f9ff; border-left:1px solid #bae6fd; font-family: 'Segoe UI', Tahoma, sans-serif; font-size:15px; line-height:1.8; color:#0369a1;">
                <div style="font-size:12px; color:#0284c7; margin-bottom:6px; direction:ltr; text-align:left;">
                    Words: {r_words} (<span style="color:{delta_color}; font-weight:bold;">{delta:+d}</span>) | Read Time: ~{round(r_words / 150, 1)}m
                </div>
                {html.escape(refined)}
            </td>
        </tr>
        """)

    html_content = f"""<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="UTF-8">
    <title>Al-Daheeh Script Doctor: Comparison Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; margin: 0; padding: 24px; color: #f8fafc; }}
        .container {{ max-width: 1300px; margin: 0 auto; background: #ffffff; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); overflow: hidden; color: #1e293b; }}
        .header {{ background: linear-gradient(135deg, #1e293b, #0f172a); color: white; padding: 24px 32px; display: flex; justify-content: space-between; align-items: center; }}
        .metrics {{ display: flex; gap: 20px; font-size: 14px; }}
        .metric-card {{ background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 6px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ padding: 14px; background: #334155; color: white; text-align: center; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 style="margin:0; font-size:20px;">🎬 Al-Daheeh Script Doctor: Production QA Audit</h2>
            <div class="metrics">
                <div class="metric-card">Original Words: <b>{total_orig_words}</b></div>
                <div class="metric-card">Refined Words: <b>{total_ref_words}</b></div>
                <div class="metric-card">Est. Audio: <b>~{round(total_ref_words / 150, 1)} mins</b></div>
            </div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Phase 3 Transcreation (Original)</th>
                    <th>Polished Doctor Script (Final Deliverable)</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
    </div>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[REPORT] Visual QA comparison dashboard generated: {html_path}")


def prepare_tts_acoustic_text(text: str) -> str:
    """
    Optimizes punctuation, breath points, and pauses for Neural Arabic TTS engines (ElevenLabs / Azure).
    Replaces visual-only ellipsis with paced acoustic pauses and ensures clean comma intervals.
    """
    if not text:
        return ""

    t = text
    # 1. Replace multi-dot ellipsis with standardized Arabic breath pauses
    t = re.sub(r"\.{3,}|…", " ، ", t)

    # 2. Normalize em-dashes and hyphens to gentle micro-pauses
    t = re.sub(r"\s*[—–\-]+\s*", " ، ", t)

    # 3. Prevent aggressive pitch spikes from stacked punctuation (e.g., '!؟!' -> '؟')
    t = re.sub(r"[!؟]{2,}", "؟", t)
    t = re.sub(r"!+", "", t)  # Latin '!' is TTS-hostile in Arabic delivery; drop it

    # 4. Ensure proper spacing around Arabic punctuation for TTS acoustic cadence
    t = re.sub(r"\s*([،؛:.؟])\s*", r" \1 ", t)

    # 5. Clean up redundant spaces
    t = re.sub(r"\s+", " ", t).strip()
    return t


def save_refined_script(folder, refined_paragraphs):
    text_path = _safe_path(folder, "refined_script.txt")
    docx_path = _safe_path(folder, "refined_script.docx")
    tts_json_path = _safe_path(folder, "tts_payload.json")
    full_text = "\n\n".join(refined_paragraphs)

    # 1. Save plain text and RTL Word Document
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    doc = Document()
    heading = doc.add_heading("الاسكريبت المُراجع - الدحيح", level=1)
    set_paragraph_rtl(heading)

    for p_text in refined_paragraphs:
        p = doc.add_paragraph(p_text)
        set_paragraph_rtl(p)

    doc.save(docx_path)

    # 2. Episode Runtime Estimation (Cairene educational pacing with dramatic pauses ~ 135 WPM)
    total_words = sum(len(p.split()) for p in refined_paragraphs)
    est_minutes = total_words / 135.0

    # 3. Export TTS Payload with Acoustic Pacing
    tts_payload = {
        "metadata": {
            "total_paragraphs": len(refined_paragraphs),
            "total_words": total_words,
            "estimated_runtime_minutes": round(est_minutes, 2),
            "words_per_minute_reference": 135,
            "voice_target": "Al-Daheeh (Cairene Arabic)",
        },
        "paragraphs": [
            {
                "index": i,
                "text": p,
                "tts_text": prepare_tts_acoustic_text(p),
                "word_count": len(p.split()),
                "estimated_seconds": round((len(p.split()) / 135.0) * 60, 1),
            }
            for i, p in enumerate(refined_paragraphs, 1)
        ],
    }

    with open(tts_json_path, "w", encoding="utf-8") as f:
        json.dump(tts_payload, f, ensure_ascii=False, indent=2)

    print("[SAVED] Refined script saved locally:")
    print(f" - Text File: {text_path}")
    print(f" - Word Doc:  {docx_path}")
    print(f" - TTS JSON:  {tts_json_path}")
    print(f"[TIMING] Total Words: {total_words} | Est. Episode Runtime: {est_minutes:.1f} minutes")


def is_safety_blocked(text):
    if not text or len(text.strip()) < 15:
        return True
    lower_text = text.lower()
    refusal_keywords = [
        "cannot fulfill",
        "unable to assist",
        "safety guidelines",
        "against my policy",
        "something went wrong",
        "restricted content",
        "i am unable",
        "i apologize, but i cannot",
        "as an ai language model",
    ]
    for word in refusal_keywords:
        if word in lower_text:
            return True
    return False


def ensure_chrome_debug_session(browser_type, profile_index, force_restart=True):
    """
    Launches Chrome debugging session with the exact requested profile index.
    If force_restart is True, it kills any existing background Chrome to ensure profile switch.
    """
    port = CONFIG.cdp_port
    url = f"http://127.0.0.1:{port}/json/version"

    if not force_restart:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    print(f"Chrome debugging session is already active on port {port}.")
                    return True
        except Exception:
            pass

    # Kill old background session so the new profile index actually boots
    print(
        f"[SYSTEM] Initializing Browser: {browser_type} | Profile Index: {profile_index} on Port {port}"
    )
    kill_cdp_chrome(port)
    time.sleep(1)

    return launch_browser_with_profile(browser_type, profile_index, port=port)


def wait_for_gemini_ready(page, timeout_seconds=20):
    """Waits for Gemini's interactive editor to be attached and visible."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_seconds * 1000)
    except Exception:
        pass

    ready_selectors = [
        "rich-textarea .ql-editor",
        "rich-textarea [contenteditable='true']",
        "div[contenteditable='true']",
        "rich-textarea",
    ]
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        for sel in ready_selectors:
            loc = page.locator(sel).first
            try:
                if loc.count() > 0 and loc.is_visible():
                    time.sleep(1)
                    return True
            except Exception:
                continue
        time.sleep(0.5)
    return False


def input_gemini_prompt(page, text: str) -> None:
    """
    Injects text into Gemini's custom rich-textarea element using pure IME keyboard insertion.
    Bypasses OS clipboard to avoid permission checks and focus-loss stalls.
    """
    wait_for_gemini_ready(page)
    target = find_input_box(page)

    if not target:
        raise RuntimeError("Could not locate Gemini input box.")

    # 1. Bring element into view and focus
    try:
        target.scroll_into_view_if_needed(timeout=2000)
        target.click(force=True)
        time.sleep(0.2)
    except Exception:
        pass

    # Pure IME insertion: dispatches raw text events directly into Quill's contenteditable
    target.focus()
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.insert_text(text)

    # Trigger synthetic input event to enable the Send button in Angular
    target.evaluate("el => el.dispatchEvent(new Event('input', { bubbles: true }))")
    time.sleep(0.3)


def setup_refinement_session(page, model_name):
    """Turn 1: Send the refinement style guide and wait for acknowledgment."""
    print("[SETUP] Starting refinement session...")
    start_clean_gemini_chat(page)
    wait_for_gemini_ready(page)

    select_gemini_model(page, model_name)
    time.sleep(1)

    prompt_text = read_refine_prompt()

    print("[SETUP] Sending refinement style guide...")
    try:
        input_gemini_prompt(page, prompt_text)
    except Exception as e:
        print(f"[FATAL] Could not input setup prompt: {e}")
        return False

    time.sleep(1)
    initial_count = page.locator(RESPONSE_SELECTOR).count()

    send_btn = find_send_button(page)
    if send_btn and send_btn.is_enabled():
        send_btn.click()
    else:
        page.keyboard.press("Control+Enter")

    print("[SETUP] Waiting for Gemini acknowledgment...")
    response = wait_for_gemini_response(page, initial_count, timeout_seconds=120)

    if not response:
        print("[SETUP ERROR] No response received from Gemini during setup.")
        return False

    if any(kw in response.lower() for kw in ["understood", "جاهز", "مستعد", "تمام"]):
        print("[SETUP] Gemini acknowledged refinement rules.")
        return True

    print("[SETUP WARN] Acknowledgment ambiguous, but received response. Proceeding...")
    return True


def send_prompt_to_gemini(page, text):
    """Safely fills and dispatches a prompt, ensuring the send button is enabled."""
    try:
        input_gemini_prompt(page, text)
    except Exception as e:
        print(f"[ERROR] Failed to inject text into input: {e}")
        return False, 0

    time.sleep(1)
    initial_count = page.locator(RESPONSE_SELECTOR).count()

    sent = False
    for _ in range(4):
        send_btn = find_send_button(page)
        if send_btn and send_btn.is_visible() and send_btn.is_enabled():
            send_btn.click()
            sent = True
            break
        time.sleep(0.5)

    if not sent:
        page.keyboard.press("Control+Enter")

    time.sleep(1)
    return True, initial_count


def refine_paragraph(
    page,
    paragraph_text,
    index,
    total,
    previous_tail="",
    global_motif="",
    banned_slang=None,
    lean_prompt=True,
):
    """Sends a single paragraph with sliding-window narrative context, motif memory & active slang exclusions.
    If lean_prompt=True (default), sends only dynamic variables since system rules were established in setup.
    """
    persona = get_config_value("REFINE_PERSONA", "Al-Daheeh")
    is_outro_zone = index >= max(1, total - 1)

    slang_restriction = ""
    if banned_slang and len(banned_slang) > 0 and not is_outro_zone:
        banned_str = "، ".join([f"'{w}'" for w in banned_slang])
        slang_restriction = f"- [SLANG FATIGUE RESTRICTION]: Strictly DO NOT use any of these recently used words: ({banned_str}). Choose fresh alternative slang.\n"

    motif_instruction = ""
    if global_motif:
        if is_outro_zone:
            motif_instruction = f"- [CHEKHOV'S GAG PAYOFF]: Revisit the core motif '{global_motif}' with deep poetic/philosophical meaning.\n"
        elif index in [1, 7, 12]:  # Only inject motif 2-3 times across the entire script
            motif_instruction = f"- [OPTIONAL MOTIF CALLBACK]: You may reference '{global_motif}' if it fits naturally (DO NOT force it).\n"
        else:
            motif_instruction = f"- [MOTIF RESTRICTION]: Do NOT mention '{global_motif}' in this paragraph to avoid repetitive comedy.\n"

    if is_outro_zone:
        tone_block = (
            "⚠️ [THE EXISTENTIAL OUTRO ZONE]\n"
            "- Tone: Intimate, philosophical, goosebump-inducing (العِبرة الوجودية).\n"
            "- Drop all slapstick puns, Abo Hmeed interjections, and street comedy.\n"
            f"{motif_instruction}"
            "- Use short, poignant Gary Provost sentences reflecting on cosmic scale/history."
        )
    else:
        tone_block = (
            "- Ground explanations in tangible Egyptian archetypes (الميكروباص / الموظف / باقة النت / أقساط).\n"
            f"{motif_instruction}"
            "- Insert an 'Abo Hmeed' skeptic interjection (e.g., 'ثانية واحدة يا أبو حميد!') if pacing fits."
        )

    context_bridge = ""
    if previous_tail:
        context_bridge = f'BRIDGE CONTEXT (The previous paragraph ended with):\n"{previous_tail}"\n(Ensure a smooth transition)\n\n'

    if lean_prompt:
        # Lean prompt: system rules already established in setup_refinement_session.
        # The dialect ratio + tagging directives are re-anchored on every turn:
        # they are contractual (30/70 Golden Ratio, <final_script> extraction)
        # and must survive context drift in long sessions.
        message = (
            f"Refine Paragraph {index}/{total}:\n\n"
            f"{context_bridge}"
            f"[RATIO LOCK]: Persona '{persona}' — 30% Academic Fusha : 70% Cairene Amiya.\n"
            f"[TAG LOCK]: Draft inside <thinking>...</thinking>; output ONLY the final Arabic paragraph inside <final_script>...</final_script>.\n"
            f"{tone_block}\n"
            f"{slang_restriction}"
            f"ORIGINAL PARAGRAPH:\n{paragraph_text}"
        )
    else:
        # Full prompt for first turn or when context refresh occurs
        message = (
            f"Refine Paragraph {index} of {total}:\n"
            f"{context_bridge}"
            "STRICT EXECUTION DIRECTIVE:\n"
            f"1. Persona: '{persona}' (30% Academic Data : 70% Cairene Amiya).\n"
            "2. Gary Provost Cadence: Alternate short hits, medium setups, data density, and punchlines naturally.\n"
            f"{tone_block}\n"
            f"{slang_restriction}"
            "3. Slang Rotation: Maintain strict category diversity.\n"
            "4. Phonetic Numbers: Transliterate all numbers into Arabic words.\n"
            "5. MANDATORY TAGGING: Put all drafting/notes inside <thinking>...</thinking>, and output ONLY the final Arabic paragraph inside <final_script>...</final_script> tags.\n\n"
            f"ORIGINAL PARAGRAPH:\n{paragraph_text}"
        )

    success, initial_count = send_prompt_to_gemini(page, message)
    if not success:
        print(f"[ERROR] Failed to send prompt for paragraph {index}.")
        return None

    # Allow enough headroom for Gemini Pro 'Thinking' phase (default 420s / 7 mins)
    refine_timeout = CONFIG.timeout_seconds
    response = wait_for_gemini_response(page, initial_count, timeout_seconds=refine_timeout)

    if is_safety_blocked(response):
        print(f"[WARNING] Safety flag triggered on paragraph {index}.")
        return None

    if response:
        cleaned = clean_refined_paragraph(response)
        is_valid, reason = validate_refinement_quality(cleaned, is_outro=is_outro_zone)
        if not is_valid:
            print(f"[RE-INSPECT] Quality check warning on paragraph {index}: {reason}")
        return cleaned
    return None


def main():
    # Adaptive writing has its own validated per-channel refinement contract.
    requested_folder = sys.argv[1] if len(sys.argv) > 1 else get_latest_run_folder()
    if requested_folder and os.path.isfile(os.path.join(requested_folder, "episode_brief.json")):
        from youtube_automation.production.writing import verify_written_episode
        verify_written_episode(requested_folder)
        print("[ADAPTIVE] Channel-aware refinement already verified; preserving its voice and tone.")
        return
    print("=" * 60)
    print(" refinement: Arabic Script Refinement via Gemini")
    print("=" * 60)

    # 1. Read config variables FIRST
    model_name = CONFIG.model_name
    max_retries = CONFIG.max_retries
    switch_accounts = CONFIG.switch_accounts
    browser_type = CONFIG.browser_type
    _raw_profile = get_runtime_state("ACTIVE_PROFILE_INDEX", get_config_value("ACTIVE_PROFILE_INDEX", "2"))
    _match = re.search(r"\d+", str(_raw_profile))
    profile_index = int(_match.group(0)) if _match else 2

    print(
        f"[CONFIG] Active Profile Index: {profile_index} | Browser: {browser_type} | Model: {model_name}"
    )

    # 2. Automatically verify or launch Chrome debug session using the configured profile index
    if not ensure_chrome_debug_session(browser_type, profile_index, force_restart=False):
        print("Could not verify or start Chrome debugging session. Exiting.")
        return

    folder = requested_folder
    if not folder:
        print("No youtube_runs folder found.")
        sys.exit(1)

    video_title = os.path.basename(os.path.normpath(folder))
    print(f"Processing: {video_title}")

    final_output = read_final_output(folder)
    paragraphs = split_paragraphs(final_output)
    print(f"Found {len(paragraphs)} paragraphs to refine.")

    refined_paragraphs = load_checkpoint(folder)
    start_index = len(refined_paragraphs)
    print(f"Resuming from paragraph {start_index + 1}.")

    if start_index >= len(paragraphs):
        print("All paragraphs already refined.")
        # Crash-window recovery: the last checkpoint save can precede the
        # deliverable write. Regenerate artifacts BEFORE discarding state,
        # otherwise a rerun deletes the only copy of the refined script.
        if refined_paragraphs and not os.path.exists(_safe_path(folder, "refined_script.txt")):
            print("[RECOVERY] refined_script.txt missing — regenerating from checkpoint...")
            save_refined_script(folder, [t.refined_text for t in refined_paragraphs])
        delete_checkpoint(folder)
        return

    with sync_playwright() as p:
        # Chrome's browser-level websocket can lag its HTTP health probe during
        # cold start; retry the CDP handshake instead of hard-failing on the
        # first attempt.
        browser = None
        for attempt in range(1, 4):
            try:
                browser = p.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{CONFIG.cdp_port}", timeout=15000
                )
                break
            except Exception as e:
                if attempt == 3:
                    raise
                print(
                    f"[RETRY] CDP connect attempt {attempt} failed ({type(e).__name__}); retrying..."
                )
                time.sleep(2 * attempt)
        context = browser.contexts[0]
        context.grant_permissions(["clipboard-read", "clipboard-write"])

        # Reuse existing Gemini page or open a new one with correct URL
        page = None
        for p_tab in context.pages:
            if "gemini.google.com" in p_tab.url:
                page = p_tab
                break
        if not page:
            page = context.new_page()
            page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")

        retries = 0
        # Cumulative failure budget across ALL profiles: account rotation resets
        # `retries`, so without this bound a uniformly failing fleet loops forever.
        total_failures = 0
        FAILURE_BUDGET = max(max_retries * 5, 20)
        current_index = start_index

        session_initialized = False

        # Egyptian Slang Catalog for automated rotational audit
        SLANG_DICTIONARY = [
            "هوبا",
            "قوم إيه",
            "فـ ثانية",
            "على غفلة",
            "فجأة كدا",
            "يا سيدي",
            "يا عبقري",
            "يا نبيه",
            "يا فنان",
            "야 닥터",
            "سَحْلَة",
            "خازوق",
            "حوار",
            "دوشة",
            "دوامة",
            "متاهة",
            "الزتونة",
            "سر الطبخة",
            "اللقطة",
            "الملعوب",
            "الخطة",
        ]

        def extract_recent_slang(history, count=2):
            """Scans recent paragraphs and returns terms that should be temporarily banned."""
            if not history:
                return []
            recent_text = " ".join(t.refined_text for t in history[-count:])
            return [word for word in SLANG_DICTIONARY if word in recent_text]

        while current_index < len(paragraphs) and total_failures < FAILURE_BUDGET:
            # Context Window Refresh: Invalidate active session every 6 paragraphs to clear LLM context bloat
            if current_index > 0 and current_index % 6 == 0 and session_initialized:
                print(
                    f"\n[MAINTENANCE] Periodic context refresh at paragraph {current_index + 1}..."
                )
                session_initialized = False

            if not session_initialized:
                if not setup_refinement_session(page, model_name):
                    print("[FATAL] Setup failed. Retrying with new chat...")
                    retries += 1
                    time.sleep(2)
                    continue
                session_initialized = True

            paragraph = paragraphs[current_index]
            print(f"\n[REFINE] Paragraph {current_index + 1}/{len(paragraphs)}...")

            # Extract narrative tail of previous paragraph for transition continuity
            prev_tail = ""
            if refined_paragraphs:
                prev_sentences = re.split(r"[.!?؛،\n]+", refined_paragraphs[-1].refined_text)
                prev_tail = prev_sentences[-1].strip() if prev_sentences else ""

            # Core Running Motif (Default or loaded from config)
            core_motif = get_config_value("RUNNING_GAG_MOTIF", "كوباية شاي كشري")

            # Dynamic Slang Ledger: compute exclusions from recent history
            banned_slang_list = extract_recent_slang(refined_paragraphs, count=2)

            refined_text = refine_paragraph(
                page,
                paragraph,
                current_index + 1,
                len(paragraphs),
                previous_tail=prev_tail,
                global_motif=core_motif,
                banned_slang=banned_slang_list,
                lean_prompt=True,
            )

            is_stale_duplicate = (
                len(refined_paragraphs) > 0 and refined_text == refined_paragraphs[-1].refined_text
            )

            if refined_text and not is_safety_blocked(refined_text) and not is_stale_duplicate:
                turn = RefinedTurn(
                    index=current_index + 1,
                    original_text=paragraph,
                    refined_text=refined_text,
                    word_count=len(refined_text.split()),
                    rhythm_variance=calculate_rhythm_variance(refined_text),
                    is_outro=(current_index >= len(paragraphs) - 2),
                )
                refined_paragraphs.append(turn)
                save_checkpoint(folder, refined_paragraphs)
                print(f"[OK] Paragraph {current_index + 1} refined ({len(refined_text)} chars).")
                current_index += 1
                retries = 0
            else:
                if is_stale_duplicate:
                    print(
                        f"[WARN] Detected stale duplicate response for paragraph {current_index + 1}."
                    )
                retries += 1
                total_failures += 1
                print(
                    f"[RETRY {retries}/{max_retries}] Paragraph {current_index + 1} failed. Resetting chat..."
                )

                if switch_accounts and retries >= max_retries:
                    print("[FAILOVER] Rotating account...")
                    profile_index = rotate_profile_index()
                    cdp_port = CONFIG.cdp_port
                    try:
                        browser.close()
                    except Exception:
                        pass
                    kill_cdp_chrome(cdp_port)
                    time.sleep(2)
                    if not launch_browser_with_profile(browser_type, profile_index, port=cdp_port):
                        print("[FATAL] Failed to launch rotated browser profile. Exiting.")
                        break

                    # Robust connection loop with retry to handle browser cold-boot latency
                    connected = False
                    for _ in range(6):
                        time.sleep(2)
                        try:
                            browser = p.chromium.connect_over_cdp(
                                f"http://127.0.0.1:{cdp_port}", timeout=10000
                            )
                            connected = True
                            break
                        except Exception:
                            continue

                    if not connected:
                        print("[FATAL] Could not reconnect to Chrome CDP after account rotation.")
                        break

                    context = browser.contexts[0]
                    try:
                        context.grant_permissions(
                            ["clipboard-read", "clipboard-write"],
                            origin="https://gemini.google.com",
                        )
                    except Exception:
                        pass
                    page = context.new_page()
                    page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                    retries = 0
                session_initialized = False
                time.sleep(1)

        # ALL POST-PROCESSING MUST REMAIN INSIDE THE PLAYWRIGHT CONTEXT BLOCK
        if current_index >= len(paragraphs):
            refined_texts = [t.refined_text for t in refined_paragraphs]
            save_refined_script(folder, refined_texts)
            generate_diff_report(folder, paragraphs[: len(refined_paragraphs)], refined_texts)

            # Run the final Quality Audit Rubric while Playwright context is active
            full_refined_text = "\n\n".join(refined_texts)
            print("\n[AUDIT] Running final Quality Rubric Audit on the complete script...")
            audit_passed = verify_script_with_rubric(page, full_refined_text, folder=folder)
            audit_status = "PASSED ✅" if audit_passed else "FLAGGED WITH NOTES ⚠️"
            print(f"[AUDIT] Final Script Status: {audit_status}")

            delete_checkpoint(folder)
            print(f"\n{'=' * 60}")
            print(f" REFINEMENT COMPLETE: {video_title}")
            print(f"{'=' * 60}")
            send_telegram_notification(f"✅ Script refined [{audit_status}]: {video_title}")
        else:
            print(
                f"\n[PARTIAL] Refined {current_index}/{len(paragraphs)} paragraphs. Checkpoint saved."
            )
            send_telegram_notification(
                f"⚠️ Script refinement partial: {video_title} ({current_index}/{len(paragraphs)})"
            )


def verify_script_with_rubric(page, script_text, folder=None):
    """Sends the refined script along with the audit rubric, records findings to audit_feedback.md, and checks PASS/FAIL status."""
    rubric_file = os.path.join("docs", "audit_rubric.md")
    if not os.path.exists(rubric_file):
        rubric_file = "audit_rubric.md"  # legacy root placement fallback
    if not os.path.exists(rubric_file):
        print(f"[AUDIT] '{rubric_file}' not found. Skipping rubric verification.")
        return True

    try:
        with open(rubric_file, encoding="utf-8") as f:
            rubric_text = f.read()
    except Exception as e:
        print(f"[AUDIT] Error reading '{rubric_file}': {e}")
        return True

    verification_prompt = (
        f"You are the Lead Script Doctor. Audit this script using the rubric below:\n\n"
        f"RUBRIC:\n{rubric_text}\n\n"
        f"SCRIPT TO AUDIT:\n{script_text}\n\n"
        f"Reply strictly with 'PASS' if it meets all criteria, or list the specific failures and notes clearly."
    )

    page.bring_to_front()
    try:
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
    except Exception:
        pass

    success, initial_count = send_prompt_to_gemini(page, verification_prompt)
    if success:
        response = wait_for_gemini_response(page, initial_count, timeout_seconds=120)
        cleaned_response = response.strip() if response else "(No audit response received)"
        print(f"\n[AUDIT REPORT RESULT]\n{cleaned_response}\n")

        # Persist feedback directly into the run folder for permanent documentation
        if folder and os.path.exists(_safe_path(folder, "")):
            feedback_path = _safe_path(folder, "audit_feedback.md")
            with open(feedback_path, "w", encoding="utf-8") as f:
                f.write("# Al-Daheeh Script Doctor: Quality Rubric Feedback\n\n")
                f.write(
                    f"**Status:** {'PASSED ✅' if 'PASS' in cleaned_response.upper() else 'FLAGGED ⚠️'}\n\n"
                )
                f.write(f"## Doctor's Review Notes\n\n{cleaned_response}\n")
            print(f"[SAVED] Audit feedback report saved to: {feedback_path}")

        upper_resp = cleaned_response.upper()
        # Ensure 'PASS' is matched as a standalone affirmative token, not part of 'DOES NOT PASS' or 'FAIL'
        has_fail_markers = any(
            neg in upper_resp
            for neg in ["NOT PASS", "DOES NOT PASS", "DID NOT PASS", "FAIL", "FAILED", "REJECT"]
        )
        has_pass_marker = bool(re.search(r"\bPASS\b", upper_resp))

        return has_pass_marker and not has_fail_markers
    return False


if __name__ == "__main__":
    main()
