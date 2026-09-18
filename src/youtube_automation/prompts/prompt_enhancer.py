"""Socratic Prompt Enhancer Module.

Operationalizes the 5 empirical NotebookLM Socratic prompt engineering rules:
1. Modular prompt scaffolding & single-generation inference pass
2. 1-2-3 shape hierarchy (primary silhouette, sub-structures, small accents)
3. Da Vinci Sfumato chiaroscuro lighting against desaturated negative space
4. Orthographic flat 2D projection plane with telephoto equivalent perspective (zero barrel distortion, zero keystoning)
5. Strict negative latent suppression (~94% compliance filter)
6. English-only compliance (ADR 0003: zero raw Arabic characters in diffusion prompts)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from typing import Any

from youtube_automation.prompts.validator import (
    STRICT_NEGATIVE_PROMPT,
    FrameItem,
    VisualPrompt,
    flatten_visual_prompt_to_diffusion_text,
    purge_subtitle_phrases,
    transliterate_arabic_fallback,
    validate_english_only_prompt,
    verify_pipeline_integrity,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Strategy 1: Visual Style Anchor Lockdown (Modern 2D Comic Vector DNA)
MASTER_POSITIVE_STYLE_DNA: str = (
    "High-end 2D graphic vector animation explainer style, bold 3px black contour linework, "
    "flat 2-step cel-shading, locked neutral studio substrate ground (#F8F8FA), "
    "balanced 16:9 widescreen composition, sharp central subject focus, high focal clarity, "
    "1-2-3 shape hierarchy"
)

STRICT_BANNED_KEYWORDS: list[str] = [
    "technical blueprint",
    "blueprint",
    "archival document",
    "sepia vellum",
    "vellum",
    "da vinci sketchbook",
    "da vinci",
    "leonardo da vinci",
    "bistre wash",
    "cross-hatching",
    "oil painting",
    "photorealistic",
    "photorealism",
    "3D CGI",
    "octane render",
    "retro blueprint",
]

SOCRATIC_STYLE_DNA = MASTER_POSITIVE_STYLE_DNA

# Unified Studio Substrates (Audit §3.2, §6.1)
LIGHT_LIMBO_SUBSTRATE: str = "neutral light studio limbo ground (#F8F8FA)"
AHWA_STUDIO_GROUND: str = "warm dark mahogany studio workbench (#2A2420)"

# Chromatic Attention Law (60-30-10) & Codec-Safe Accents (Audit §6.1, §6.2)
CODEC_SAFE_RED: str = "#EB191E"  # RGB(235, 25, 30) prevents 4:2:0 chroma subsampling bleeding
STRUCTURAL_CHARCOAL: str = "#2D3444"
ACCENT_ELECTRIC_CYAN: str = "#00E5FF"
ACCENT_AMBER: str = "#FFB300"
ACCENT_SPRING_GREEN: str = "#00E676"

CHROMATIC_PALETTE_60_30_10: str = (
    "Palette: 60% base ground, 30% charcoal lines, "
    "10% kinetic accents (Electric Cyan #00E5FF, Amber #FFB300, Spring Green #00E676, Codec-Safe Red #EB191E)"
)

SOCRATIC_LIGHTING_DNA = (
    "high-key clean studio illumination, sharp contrast, razor-sharp shadow falloff, zero gradients on locked studio substrate"
)

SOCRATIC_CAMERA_DNA = (
    "clean 16:9 widescreen composition strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 980, "
    "leaving 10% peripheral bleed padding for automated pan and zoom, level eye-line perspective, "
    "orthographic flat 2D projection plane, zero barrel distortion, zero keystoning, telephoto equivalent perspective"
)

# Strategy 2: Two-Tier Text Quarantine Negative Token Suppression
STRICT_ZERO_TEXT_NEGATIVE: str = (
    "no text, no letters, no words, no alphabet, no labels, no watermark, no logo, "
    "no signs, no writing, no typography, no captions, no subtitles, no burned subtitles, "
    "no chalkboard, no specular glare, no English, "
    "no numbers, no equations, no diagrams with text, no alphanumeric characters, "
    "no technical blueprint, no architectural CAD, no engineering drawings, "
    "no sepia vellum, no da vinci sketchbook, no parchment, no dirty background, "
    "no sfumato, "
    "no 24mm lens, no wide-angle lens, no wide-angle distortion, no fisheye, no barrel distortion, no keystone distortion, "
    "no saturated pure red, no pure red RGB(255,0,0), no crushed blacks RGB(0,0,0), "
    "no oil painting, no 3D CGI, no photorealism, no realistic skin textures, "
    "no blurry details, no visual noise, no text in lower-third"
)

SOCRATIC_NEGATIVE_PROMPT: str = STRICT_ZERO_TEXT_NEGATIVE

ASSET_TOKEN_EXPANSIONS: dict[str, str] = {
    "CHARACTER_SKEPTIC_ABO_HMEED": "Abo Hmeed (The Everyday Skeptic) in 2D graphic vector animation style, animated bewildered comedic facial expression, navy casual jacket over heather-grey crewneck t-shirt",
    "CHARACTER_HOST_MAIN": "Al-Daheeh Egyptian cartoon educational host, dark curly hair, black round glasses, animated expressive comedic facial expression, 2D graphic vector animation style",
    "CHARACTER_AL_DAHEEH": "Al-Daheeh Egyptian cartoon educational host, dark curly hair, black round glasses, animated expressive comedic facial expression, 2D graphic vector animation style",
    "CHARACTER_CLERK_BUREAUCRAT": "comical Egyptian government bureaucrat in worn tan suit with thick glasses, 2D graphic vector animation style",
    "SCENE_ISOLATED_WHITE_ENV": "neutral light studio limbo ground (#F8F8FA)",
    "SCENE_AHWA_STUDIO_ENV": "traditional Egyptian Ahwa cafe studio, warm dark mahogany studio workbench (#2A2420), subtle warm atmospheric illumination",
    "SCENE_KEYNOTE_SLATE_ENV": "neutral light studio limbo desk (#F8F8FA) with an orthographic drafting placard resting flat on the surface",
    "SCENE_COMPARATIVE_DIAGRAM_ENV": "neutral light studio limbo desk (#F8F8FA) with a comparative split diagram placard resting flat on the surface",
    "SCENE_RETRO_BLUEPRINT_ENV": "neutral light studio limbo desk (#F8F8FA) with an orthographic cyan blueprint drafting placard resting flat on the surface",
    "SCENE_HISTORICAL_MUSEUM": "neutral light studio limbo desk (#F8F8FA) with an archival parchment folio resting flat on the surface",
    "SCENE_LIGHT_LIMBO_ENV": "neutral light studio limbo ground (#F8F8FA)",
    "SCENE_HOST_STUDIO_ENV": "neutral light studio limbo ground (#F8F8FA) with a clean educational presenter desk",
    "SCENE_AHWA_STUDIO_GROUND_ENV": "warm dark mahogany studio workbench (#2A2420)",
}


def expand_asset_tokens(text: str, profile: Any | None = None) -> str:
    """Expands asset preset constants into concrete 2D vector descriptions, respecting channel profile overrides."""
    if not text:
        return ""
    result = text
    expansions = dict(ASSET_TOKEN_EXPANSIONS)
    if profile is not None:
        avatar_desc = getattr(profile, "host_avatar_description", "") or ""
        if avatar_desc:
            expansions["CHARACTER_HOST_MAIN"] = avatar_desc
            expansions["CHARACTER_AL_DAHEEH"] = avatar_desc
        custom_tokens = getattr(profile, "custom_tokens", None)
        if isinstance(custom_tokens, dict):
            expansions.update(custom_tokens)
    for token, expansion in expansions.items():
        if token in result:
            result = result.replace(token, expansion)
    return result


def purge_banned_visual_keywords(text: str, profile: Any | None = None) -> str:
    """Purges all banned style keywords (blueprints, parchments, photorealism, CGI)
    and replaces them with clean 2D vector concepts."""
    if not text:
        return ""
    result = expand_asset_tokens(text, profile=profile)
    # Replace blueprint and CAD patterns with clean 2D vector graphic diagrams
    result = re.sub(r"\b(retro\s+)?blueprints?\b", "clean 2D vector graphic diagram", result, flags=re.IGNORECASE)
    result = re.sub(r"\btechnical\s+schematics?\b", "minimalist 2D vector graphic", result, flags=re.IGNORECASE)
    result = re.sub(r"\b(archival\s+documents?|sepia\s+vellum|vellum|parchments?)\b", "archival drafting folio displaying non-textual proportion diagrams", result, flags=re.IGNORECASE)
    result = re.sub(r"\b(da\s+vinci(\s+sketchbook)?|leonardo\s+da\s+vinci)\b", "clean 2D vector draughtsmanship", result, flags=re.IGNORECASE)
    result = re.sub(r"\b(bistre\s+wash|cross-hatching)\b", "flat 2-step cel-shading", result, flags=re.IGNORECASE)
    result = re.sub(r"\b(oil\s+painting|photorealistic|photorealism|3D\s+CGI|octane\s+render)\b", "2D graphic vector animation", result, flags=re.IGNORECASE)
    # Purge equations / mathematical formulas in prompt to prevent diffusion model from drawing English CAD letters
    result = re.sub(r"\b(mathematical\s+physics\s+formulas?|mathematical\s+equations?|multiplication\s+equations?|equations?|formulas?)\b", "abstract geometric line curves without text or numbers", result, flags=re.IGNORECASE)
    # Demote colloquial slang metaphors to peripheral corner props
    result = re.sub(
        r"\b(yellow\s+)?(microbuses?|transit\s+buses?|public\s+transport\s+buses?|minibuses?)\b",
        "miniature toy microbus prop in the peripheral desk corner",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"\b(phone\s+recharge\s+cards?|sim\s+cards?|recharge\s+vouchers?)\b",
        "small phone card prop in the peripheral desk corner",
        result,
        flags=re.IGNORECASE,
    )
    # Purge legacy 24mm and wide-angle lens tokens
    result = re.sub(
        r"\b24\s*mm(\s+wide[- ]angle)?(\s+lens|\s+optics|\s+framing)?\b|\bwide[- ]angle\s+lens\b|\bfisheye(\s+lens)?\b",
        "orthographic flat 2D projection plane",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(r"\s+", " ", result)
    return result.strip()


# ==============================================================================
# TIER 1.1: HARDENED SURFACE NEUTRALIZATION & ACTIVE DATA TELEMETRY
# ==============================================================================

# Priority 1: High-precision compound phrases (MUST match before solitary nouns)
COMPOUND_SURFACE_RULES: list[tuple[str, str]] = [
    # Circuit boards & electronics (Preserve engineering context, inject active telemetry)
    (
        r"\b(printed\s+)?circuit\s+boards?\b",
        "printed circuit schematic board with copper trace paths and glowing micro-nodes",
    ),
    (
        r"\b(motherboards?|breadboards?)\b",
        "circuit prototyping board with micro-traces and glowing indicator nodes",
    ),
    # Split-screen & interface composition (Preserve layout geometry, prevent self-duplication)
    (
        r"\bsplit[-\s]screens?(?!\s+dual\s+composition)\b",
        "split-screen dual composition with bilateral comparative panels",
    ),
    (
        r"\b(green[-\s]screens?|touch[-\s]screens?|lock[-\s]screens?)\b",
        "digital touch interface displaying vector geometry",
    ),
    # Books & ledgers (Prevent 'open closed book' antonymous state inversion)
    (
        r"\bopen(\s+retro)?\s+(books?|notebooks?|ledgers?|journals?)\b",
        "open technical reference ledger with abstract non-textual proportion charts",
    ),
    (
        r"\b(closed\s+)?(books?|notebooks?|journals?|manuals?)\b",
        "unmarked reference volume with plain cover",
    ),
    # Chalkboards / Whiteboards (guarded against re-matching dark matte chalkboard)
    (
        r"(?<!\bdark\smatte\s)\b(blackboards?|chalkboards?|whiteboards?)\b",
        "dark matte chalkboard with clean geometric diagrams and non-linguistic coordinate axes",
    ),
]

# Priority 2: Solitary nouns guarded by strict negative lookbehinds
GUARDED_SOLITARY_SURFACE_RULES: list[tuple[str, str]] = [
    # Screens / Monitors: guarded against split-, full-, green-, touch-, lock-, telemetry
    (
        r"(?<!\bsplit-)(?<!\bsplit\s)(?<!\bfull-)(?<!\bfull\s)(?<!\bgreen\s)(?<!\btouch\s)(?<!\block\s)(?<!\btelemetry\s)"
        r"\b(screens?|displays?|monitors?|televisions?|tvs?)\b",
        "digital telemetry display with abstract waveform traces and glowing coordinate nodes",
    ),
    # Display boards / easels: guarded against circuit, mother, bread, dash, story, cutting, chalk, white, black, key, schematic, prototyping, display
    (
        r"(?<!\bcircuit\s)(?<!\bmother)(?<!\bbread)(?<!\bdash)(?<!\bstory)(?<!\bcutting)"
        r"(?<!\bchalk)(?<!\bwhite)(?<!\bblack)(?<!\bkey)(?<!\bschematic\s)(?<!\bprototyping\s)(?<!\bdisplay\s)"
        r"\b(signboards?|plaques?|boards?|billboards?|banners?|posters?)\b",
        "unmarked wooden display easel",
    ),
    # Placards / Documents: convert dead blank paper to active drafting placards
    (
        r"\b(papers?|documents?|parchments?|dossiers?|sheets?)\b",
        "drafting placard displaying abstract non-textual ratio diagrams",
    ),
    # Insignias / Stamps: guarded against wax seal
    (
        r"(?<!\bwax\s)\b(stamps?|seals?|badges?|labels?|tags?)\b",
        "stylized wax seal emblem",
    ),
    # Schematics / Blueprints: guarded against circuit, vector
    (
        r"(?<!\bvector\s)(?<!\bcircuit\s)\b(schematics?|blueprints?|cad\s+drawings?)\b",
        "orthographic vector schematic with abstract node linkages",
    ),
    # Formulas / Math: replace with active geometric telemetry
    (
        r"\b(equations?|formulas?|math\s+symbols?|mathematical\s+physics\s+formulas?)\b",
        "abstract non-textual proportion bars and geometric wave curves",
    ),
]

# Priority 0: Repair rules for pre-existing corrupted dataset strings
LEGACY_CORRUPTION_REPAIR_RULES: list[tuple[str, str]] = [
    (
        r"circuit blank unmarked wooden board with zero writing",
        "printed circuit schematic board with copper trace paths and glowing micro-nodes",
    ),
    (
        r"split-blank dark glass monitor without display",
        "split-screen dual composition with bilateral comparative panels",
    ),
    (
        r"open retro blank closed book with unmarked plain cover",
        "open technical reference ledger with abstract non-textual proportion charts",
    ),
    (
        r"blank closed book with unmarked plain cover",
        "unmarked reference volume with plain cover",
    ),
    (
        r"blank dark glass monitor without display",
        "digital telemetry display with abstract waveform traces and glowing coordinate nodes",
    ),
    (
        r"clean unwritten white paper sheet",
        "drafting placard displaying abstract non-textual ratio diagrams",
    ),
    (
        r"blank unmarked wooden board with zero writing",
        "unmarked wooden display easel",
    ),
    (
        r"blank unmarked dark chalkboard with clean matte surface",
        "dark matte chalkboard with clean geometric diagrams and non-linguistic coordinate axes",
    ),
    (
        r"ornate blank brass stamping tool without lettering",
        "stylized wax seal emblem",
    ),
    # Recursive self-duplication purges
    (
        r"(clean 2D vector graphic lines with zero text\s*){1,}",
        "clean 2D vector schematics ",
    ),
    (
        r"(abstract geometric line curves without text or numbers\s*){1,}",
        "abstract non-textual proportion curves ",
    ),
    (
        r"\bdiagram\s+diagram\b",
        "diagram",
    ),
]


def neutralize_surfaces(text: str) -> str:
    """Neutralizes textual surfaces, eliminating Latin text leaks while replacing
    dead blank boards/screens with active abstract non-linguistic data telemetry.
    Mathematically idempotent: neutralize_surfaces(neutralize_surfaces(text)) == neutralize_surfaces(text).
    """
    if not text:
        return ""

    result = text

    # Step 0: Purge legacy corrupted phrases first
    for pattern, repl in LEGACY_CORRUPTION_REPAIR_RULES:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)

    # 1. Strip quoted English phrases like 'REJECTED', 'CRITICAL', "CONFIDENTIAL", 'START', 'FINISH'
    result = re.sub(r"['\"][^'\"]*['\"]", "", result)

    # Step 2: Execute compound surface substitutions
    for pattern, repl in COMPOUND_SURFACE_RULES:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)

    # Step 3: Execute guarded solitary surface substitutions
    for pattern, repl in GUARDED_SOLITARY_SURFACE_RULES:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)

    # Step 4: De-duplicate consecutive duplicated telemetry phrases
    result = re.sub(r"\b(clean 2D vector schematics\s*){2,}", "clean 2D vector schematics ", result)
    result = re.sub(r"\b(digital telemetry display\s*){2,}", "digital telemetry display ", result)
    result = re.sub(
        r"\b(drafting placard displaying abstract non-textual ratio diagrams\s*){2,}",
        "drafting placard displaying abstract non-textual ratio diagrams ",
        result,
    )

    # Step 5: Normalize whitespaces and trailing punctuation
    result = re.sub(r"\s+", " ", result).strip()
    result = re.sub(r"\s+([,.:;])", r"\1", result)
    return result


MAD_CONTRADICTORY_NEGATIVE_TOKENS: set[str] = {
    "3px", "no 3px", "3 px", "no 3 px",
    "vector", "no vector",
    "cel-shading", "no cel-shading", "cel shading", "no cel shading",
    "contour", "contour linework",
    "linework", "2d graphic", "graphic vector",
    "clean lines", "sharp lines",
    "orthographic", "no orthographic",
    "telephoto", "no telephoto",
    "2d", "no 2d",
}


def _split_negative_tokens(text: str) -> list[str]:
    """Splits negative prompt strings on commas while preserving parenthesized tuples like RGB(255,0,0)."""
    tokens: list[str] = []
    current: list[str] = []
    in_paren = False
    for char in text:
        if char == "(":
            in_paren = True
        elif char == ")":
            in_paren = False
        if char == "," and not in_paren:
            tok = "".join(current).strip()
            if tok:
                tokens.append(tok)
            current = []
        else:
            current.append(char)
    tok = "".join(current).strip()
    if tok:
        tokens.append(tok)
    return tokens


def sanitize_negative_prompt(user_negative: str = "") -> str:
    """Builds a deterministic, de-duplicated negative prompt free of MAD token contradictions."""
    tokens: set[str] = set()

    for tok in _split_negative_tokens(STRICT_NEGATIVE_PROMPT):
        cleaned = tok.strip()
        if cleaned and cleaned.lower() not in MAD_CONTRADICTORY_NEGATIVE_TOKENS:
            tokens.add(cleaned)

    for tok in _split_negative_tokens(STRICT_ZERO_TEXT_NEGATIVE):
        cleaned = tok.strip()
        if cleaned and cleaned.lower() not in MAD_CONTRADICTORY_NEGATIVE_TOKENS:
            tokens.add(cleaned)

    if user_negative:
        for tok in _split_negative_tokens(user_negative):
            cleaned = tok.strip()
            norm = re.sub(r"^no\s+", "", cleaned, flags=re.IGNORECASE).strip().lower()
            if cleaned and cleaned.lower() not in MAD_CONTRADICTORY_NEGATIVE_TOKENS and norm not in MAD_CONTRADICTORY_NEGATIVE_TOKENS:
                tokens.add(cleaned)

    return ", ".join(sorted(tokens))


def build_mode_a_prompt(
    subject: str,
    spatial_direction: str = "centered focal composition",
    setting: str = "SCENE_LIGHT_LIMBO_ENV",
    domain_palette: str = "TECHNICAL_SLATE",
    niche: str = "GENERAL_EXPLAINER",
    telemetry_type: str = "PROPORTIONAL_RATIO_METERS",
    framing_scale: str = "",
    channel_profile: Any | None = None,
) -> str:
    """
    Builds a Mode A Master Anchor Setup prompt (70-110 words) using the Inverted Pyramid Universal Prompt Grammar:
    Zone 1: Primary Semantic Entity & Action (Tokens 1-35) -> Subject & framing first for maximum diffusion attention
    Zone 2: Spatial Staging & Telemetry (Tokens 36-55) -> 16:9 widescreen layout & non-linguistic data telemetry
    Zone 3: Niche Substrate Ground (Tokens 56-75) -> Environment & 60-30-10 palette
    Zone 4: Master Style Anchor & Optics (Tokens 76-95) -> 2D vector cel-shading & orthographic optical plane
    """
    from youtube_automation.prompts.niche_engine import (
        SPATIAL_LAYOUT_PRESETS,
        TELEMETRY_PRESETS,
        get_niche_preset,
    )

    niche_preset = get_niche_preset(niche)
    clean_subj = purge_banned_visual_keywords(
        neutralize_surfaces(_ensure_english_text(purge_subtitle_phrases(subject))),
        profile=channel_profile,
    )

    # Zone 1: Primary Semantic Entity & Action (Tokens 1-35, Highest Attention Weight)
    prefix_framing = (
        f"{framing_scale} framing of "
        if framing_scale and not any(clean_subj.lower().startswith(x) for x in ["ms ", "mcu ", "cu ", "ws ", "ews ", "wide ", "close-up", "medium "])
        else ""
    )
    zone1 = f"{prefix_framing}{clean_subj.rstrip('.')}."

    # Zone 2: Spatial Staging & Telemetry (Tokens 36-55)
    if not spatial_direction or spatial_direction == "centered focal composition":
        spatial_desc = "Clean 16:9 widescreen composition strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 980, leaving 10% peripheral bleed padding for automated pan and zoom"
    else:
        spatial_desc = SPATIAL_LAYOUT_PRESETS.get(spatial_direction.strip().upper(), spatial_direction)
        if "16:9" not in spatial_desc and "coordinates" not in spatial_desc:
            spatial_desc = f"{spatial_desc}, coordinates X: 180 to 1740, Y: 90 to 980, leaving 10% peripheral bleed padding"

    telemetry_desc = TELEMETRY_PRESETS.get(telemetry_type.strip().upper(), niche_preset.default_telemetry)
    zone2 = f"{spatial_desc}, displaying {telemetry_desc}."

    # Zone 3: Substrate Ground & 60-30-10 Palette (Tokens 56-75)
    setting_desc = niche_preset.substrate_desc
    if setting and setting != "SCENE_LIGHT_LIMBO_ENV":
        s_lower = setting.lower()
        if setting == "SCENE_AHWA_STUDIO_ENV" or "ahwa" in s_lower or "mahogany" in s_lower:
            setting_desc = "warm dark mahogany studio workbench (#2A2420)"
        elif setting == "SCENE_HOST_STUDIO_ENV" or "host" in s_lower:
            setting_desc = "neutral light studio limbo ground (#F8F8FA) with a clean educational presenter desk"
        elif setting == "SCENE_KEYNOTE_SLATE_ENV" or "slate" in s_lower or "keynote" in s_lower:
            setting_desc = "neutral light studio limbo desk (#F8F8FA) with an orthographic drafting placard resting flat on the surface"
        elif setting == "SCENE_RETRO_BLUEPRINT_ENV" or "blueprint" in s_lower:
            setting_desc = "neutral light studio limbo desk (#F8F8FA) with an orthographic cyan blueprint drafting placard resting flat on the surface"
        elif setting == "SCENE_HISTORICAL_MUSEUM" or "museum" in s_lower or "parchment" in s_lower or "history" in s_lower:
            setting_desc = "archival map research table (#EFECE6) with drafting placards resting flat on the surface"
        elif setting == "SCENE_COMPARATIVE_DIAGRAM_ENV" or "comparative" in s_lower:
            setting_desc = "neutral light studio limbo desk (#F8F8FA) with a comparative split diagram placard resting flat on the surface"
        elif setting == "SCENE_ISOLATED_WHITE_ENV" or "white" in s_lower:
            setting_desc = "isolated clean white background (#FFFFFF)"
        elif "limbo" in s_lower:
            setting_desc = "neutral light studio limbo ground (#F8F8FA)"
        else:
            clean_setting = purge_banned_visual_keywords(neutralize_surfaces(_ensure_english_text(setting)))
            setting_desc = f"{clean_setting}, neutral light studio limbo ground (#F8F8FA)"
    elif not setting or setting == "SCENE_LIGHT_LIMBO_ENV":
        if niche == "GENERAL_EXPLAINER":
            setting_desc = "neutral light studio limbo ground (#F8F8FA)"
        else:
            setting_desc = niche_preset.substrate_desc

    palette_desc = (
        niche_preset.palette_desc
        if niche != "GENERAL_EXPLAINER"
        else "Palette: 60% base ground, 30% charcoal lines, 10% kinetic accents (Cyan #00E5FF, Amber #FFB300, Spring Green #00E676, Codec-Safe Red #EB191E)"
    )
    zone3 = f"Locked studio substrate, {setting_desc}, zero luminance strobing. {palette_desc}."

    # Zone 4: Master Style Anchor & Camera Optics (Tokens 76-95)
    zone4 = "High-end 2D graphic vector animation explainer style, uniform 3px deep charcoal (#2D3444) contour linework, flat 2-step cel-shading, zero gradients, zero text, Orthographic flat 2D projection plane, zero barrel distortion, zero keystoning, telephoto equivalent perspective."

    return f"{zone1} {zone2} {zone3} {zone4}"


def build_mode_b_prompt(
    visual_delta: str,
    spatial_direction: str = "centered",
) -> str:
    """
    Builds a Mode B Progressive Surgical Delta prompt (< 25 words) using the L.A.D. Formula.
    [Reference Lock] + [Anchor Stability] + [Single Surgical Delta]
    Strictly strips out 100% of style DNA, camera specifications, lighting descriptions,
    and negative tokens to prevent Attention Dilution (Strategy 4).
    """
    clean_delta = purge_banned_visual_keywords(neutralize_surfaces(_ensure_english_text(purge_subtitle_phrases(visual_delta)))).strip(".")
    direction = spatial_direction.strip() if spatial_direction else "centered"

    prompt = f"In the attached reference image, maintain identical subject, background, and lighting. Add {clean_delta} {direction}."
    words = prompt.split()
    if len(words) > 24:
        base_prefix = "In the attached reference image, maintain identical subject and background. Add "
        prefix_words = base_prefix.split()
        max_delta_words = 24 - len(prefix_words)
        trimmed_delta = " ".join(clean_delta.split()[:max_delta_words])
        prompt = f"{base_prefix}{trimmed_delta}."
    return prompt


def _ensure_english_text(text: str) -> str:
    """Ensures text has no raw Arabic script by applying transliteration (ADR 0003)."""
    if not text:
        return ""
    valid, _ = validate_english_only_prompt(text)
    if not valid:
        return transliterate_arabic_fallback(text)
    return text


def enhance_visual_prompt(vp: VisualPrompt | dict[str, Any]) -> VisualPrompt:
    """
    Elevates an 8-part VisualPrompt using the Modern 2D Vector Explainer Style DNA.
    Enforces Strategy 1 (Style Lockdown), Strategy 2 (Two-Tier Text Quarantine),
    and Strategy 4 (L.A.D. Delta Isolation).
    """
    if isinstance(vp, dict):
        data = dict(vp)
    else:
        data = vp.model_dump()

    # 1. English-Only Sanitization, Surface Neutralization & Banned Keyword Purge
    subject = purge_banned_visual_keywords(neutralize_surfaces(_ensure_english_text(data.get("subject") or data.get("subject_details", "")).strip()))
    action = purge_banned_visual_keywords(neutralize_surfaces(_ensure_english_text(data.get("action") or data.get("subject_action_increment", "")).strip()))
    setting = purge_banned_visual_keywords(neutralize_surfaces(_ensure_english_text(data.get("setting") or data.get("environment_coordinates", "")).strip()))
    mood = purge_banned_visual_keywords(data.get("mood", "").strip())
    lighting = purge_banned_visual_keywords(data.get("lighting", "").strip())
    composition = purge_banned_visual_keywords(data.get("composition") or data.get("composition_layout", "").strip())
    style = purge_banned_visual_keywords(data.get("style") or data.get("style_anchor", "").strip())
    user_negative = data.get("negative_prompt", "").strip()
    continuity_id = data.get("continuity_id", "").strip()

    # Normalize setting: map to Two-Substrate studio architecture
    if not setting:
        setting = "SCENE_LIGHT_LIMBO_ENV"
    elif "blueprint" in setting.lower():
        setting = "SCENE_RETRO_BLUEPRINT_ENV"
    elif "museum" in setting.lower():
        setting = "SCENE_HISTORICAL_MUSEUM"
    elif "ahwa" in setting.lower() or "host" in (data.get("subject") or "").lower():
        setting = "SCENE_AHWA_STUDIO_ENV"

    # 2. Modern 2D Vector Explainer Style Anchor Lockdown
    style = MASTER_POSITIVE_STYLE_DNA
    lighting = SOCRATIC_LIGHTING_DNA
    if not composition:
        composition = SOCRATIC_CAMERA_DNA
    elif "orthographic" not in composition.lower():
        composition = f"{composition}, {SOCRATIC_CAMERA_DNA}"

    # 3. Two-Tier Text Quarantine Negative Suppression (MAD Purged)
    ordered_negative = sanitize_negative_prompt(user_negative)

    # Purge subtitle triggers across all fields
    subject = purge_subtitle_phrases(subject)
    action = purge_subtitle_phrases(action)
    setting = purge_subtitle_phrases(setting)
    composition = purge_subtitle_phrases(composition)

    return VisualPrompt(
        subject=subject or "Al-Daheeh cartoon host",
        action=action,
        setting=setting,
        mood=mood or "dramatic, focused, engaging",
        lighting=lighting,
        composition=composition,
        style=style,
        negative_prompt=ordered_negative,
        continuity_id=continuity_id,
        # Preserve legacy fields for backward compatibility
        subject_details=subject,
        subject_action_increment=action,
        environment_coordinates=setting,
        composition_layout=composition,
        style_anchor=style,
        text_overlay_arabic="NONE",
    )


def enhance_frame_item(item: FrameItem | dict[str, Any]) -> FrameItem:
    """Enhances a FrameItem payload with Socratic prompt engineering principles."""
    if isinstance(item, dict):
        raw = dict(item)
    else:
        raw = item.model_dump()

    vp_raw = raw.get("visual_prompt", {})
    enhanced_vp = enhance_visual_prompt(vp_raw)

    seq_meta = raw.get("sequence_metadata", {})
    if not isinstance(seq_meta, dict):
        seq_meta = {"set_id": "SET_01", "frame_index": 1, "total_frames_in_set": 1}

    return FrameItem(
        index=int(raw.get("index", 1)),
        timestamp=str(raw.get("timestamp", "")),
        sequence_type=str(raw.get("sequence_type", "STANDALONE")),
        layout_classification=str(raw.get("layout_classification", "")),
        sequence_metadata=seq_meta,
        visual_density=str(raw.get("visual_density", "MINIMALIST_MACRO")),
        visual_prompt=enhanced_vp,
    )


def enhance_diffusion_prompt(
    input_data: VisualPrompt | FrameItem | dict[str, Any] | str,
    sequence_type: str = "STANDALONE",
    mode: str = "A",
    visual_delta: str = "",
    spatial_direction: str = "centered",
) -> str:
    """
    Transforms any prompt payload or raw string into an elevated, production-grade
    diffusion prompt conforming to S.S.L.C.M. (Mode A) or L.A.D. (Mode B) framework.
    """
    if mode == "B" and visual_delta:
        return build_mode_b_prompt(visual_delta, spatial_direction)

    if isinstance(input_data, str):
        # Raw string handling with surface neutralization
        cleaned_str = neutralize_surfaces(_ensure_english_text(purge_subtitle_phrases(input_data)))
        parts = [
            cleaned_str.rstrip(".") + ".",
            f"Composition: {SOCRATIC_CAMERA_DNA}.",
            f"Lighting: {SOCRATIC_LIGHTING_DNA}.",
            f"Art Style: {SOCRATIC_STYLE_DNA}.",
            f"Negative Prompt: {SOCRATIC_NEGATIVE_PROMPT}.",
        ]
        return " ".join(parts)

    if isinstance(input_data, FrameItem):
        enhanced_item = enhance_frame_item(input_data)
        return flatten_visual_prompt_to_diffusion_text(
            enhanced_item.visual_prompt.model_dump(), sequence_type=enhanced_item.sequence_type
        )

    if isinstance(input_data, VisualPrompt):
        enhanced_vp = enhance_visual_prompt(input_data)
        return flatten_visual_prompt_to_diffusion_text(
            enhanced_vp.model_dump(), sequence_type=sequence_type
        )

    if isinstance(input_data, dict):
        if "visual_prompt" in input_data and "index" in input_data:
            enhanced_item = enhance_frame_item(input_data)
            return flatten_visual_prompt_to_diffusion_text(
                enhanced_item.visual_prompt.model_dump(), sequence_type=enhanced_item.sequence_type
            )
        else:
            enhanced_vp = enhance_visual_prompt(input_data)
            return flatten_visual_prompt_to_diffusion_text(
                enhanced_vp.model_dump(), sequence_type=sequence_type
            )

    return str(input_data)


def transform_prompts_file(
    input_file: str,
    output_file: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Transforms flow_prompts.json into an elevated flow_prompts_socratic.json.
    Guarantees atomic disk writes and pipeline integrity verification.
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input prompts file does not exist: {input_file}")

    with open(input_file, encoding="utf-8") as f:
        raw_items = json.load(f)

    if not isinstance(raw_items, list):
        raise ValueError(f"Expected JSON array in {input_file}, got {type(raw_items)}")

    if limit is not None and limit > 0:
        raw_items = raw_items[:limit]

    enhanced_frames: list[FrameItem] = []
    for item in raw_items:
        enhanced_frames.append(enhance_frame_item(item))

    # Verify pipeline integrity
    payloads = [frame.model_dump() for frame in enhanced_frames]
    verify_pipeline_integrity(payloads, len(enhanced_frames))

    # Atomic write to output_file
    output_dir = os.path.dirname(os.path.abspath(output_file))
    os.makedirs(output_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output_dir, delete=False) as tf:
        json.dump(payloads, tf, ensure_ascii=False, indent=2)
        temp_name = tf.name

    os.replace(temp_name, output_file)
    return payloads


def transform_roadmap_jsonl(
    input_file: str,
    output_file: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Transforms master_roadmap.jsonl into master_roadmap_socratic.jsonl.
    Preserves all column semantics while injecting Socratic visual concepts.
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input roadmap file does not exist: {input_file}")

    rows: list[dict[str, Any]] = []
    with open(input_file, encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                row = json.loads(line_str)
                rows.append(row)
            except json.JSONDecodeError:
                continue

    if limit is not None and limit > 0:
        rows = rows[:limit]

    enhanced_rows: list[dict[str, Any]] = []
    for r in rows:
        concept = r.get("visual_concept", "")
        # Inject shape hierarchy and razor-sharp lighting into concept
        if concept and "1-2-3 shape hierarchy" not in concept:
            concept = f"{concept.rstrip('.')}. 1-2-3 shape hierarchy with razor-sharp shadow falloff, zero gradients."
        r["visual_concept"] = concept
        enhanced_rows.append(r)

    output_dir = os.path.dirname(os.path.abspath(output_file))
    os.makedirs(output_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output_dir, delete=False) as tf:
        for r in enhanced_rows:
            tf.write(json.dumps(r, ensure_ascii=False) + "\n")
        temp_name = tf.name

    os.replace(temp_name, output_file)
    return enhanced_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Socratic Prompt Enhancer CLI")
    parser.add_argument("--input", required=True, help="Path to input JSON or JSONL file")
    parser.add_argument("--output", required=True, help="Path to output enhanced file")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of frames to process")
    args = parser.parse_args()

    if args.input.endswith(".jsonl"):
        print(f"Transforming roadmap JSONL: {args.input} -> {args.output}")
        out = transform_roadmap_jsonl(args.input, args.output, limit=args.limit)
        print(f"Successfully transformed {len(out)} roadmap rows.")
    else:
        print(f"Transforming flow prompts JSON: {args.input} -> {args.output}")
        out = transform_prompts_file(args.input, args.output, limit=args.limit)
        print(f"Successfully transformed {len(out)} prompt items.")


if __name__ == "__main__":
    main()
