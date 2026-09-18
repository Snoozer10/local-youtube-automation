"""Dynamic Niche & Channel Profile Engine.

Decouples pipeline visual generation from any single hardcoded persona or culture,
providing an extensible registry of niches (Science, Finance, History, Philosophy,
General Explainer, Comedy) with specialized substrates, 60-30-10 chromatic palettes,
spatial staging models, and abstract non-linguistic telemetry archetypes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class NichePreset:
    name: str
    niche_code: str
    substrate_desc: str
    palette_desc: str
    default_telemetry: str
    accents: list[str]


@dataclass
class ChannelProfile:
    channel_name: str = "Automated Explainer Studio"
    niche: str = "GENERAL_EXPLAINER"
    host_mode: str = "NONE"  # "NONE", "CUSTOM_AVATAR", "DOCUMENTARY_OBSERVER"
    host_avatar_description: str = ""
    aspect_ratio: str = "16:9"
    custom_tokens: dict[str, str] = field(default_factory=dict)


NICHE_PRESETS: dict[str, NichePreset] = {
    "GENERAL_EXPLAINER": NichePreset(
        name="General Educational Explainer",
        niche_code="GENERAL_EXPLAINER",
        substrate_desc="neutral light studio limbo desk (#F8F8FA) with an orthographic drafting placard resting flat on the surface",
        palette_desc="Palette: 60% base ground (#F8F8FA), 30% charcoal lines (#2D3444), 10% kinetic accents (Electric Cyan #00E5FF, Amber #FFB300, Spring Green #00E676, Codec-Safe Red #EB191E)",
        default_telemetry="abstract non-textual proportion meters and flow diagrams",
        accents=["#00E5FF", "#FFB300", "#00E676", "#EB191E"],
    ),
    "SCIENCE_TECH": NichePreset(
        name="Science & Technology Explainer",
        niche_code="SCIENCE_TECH",
        substrate_desc="modern laboratory drafting workbench (#F8F8FA) with technical telemetry monitors",
        palette_desc="Palette: 60% base ground (#F8F8FA), 30% charcoal lines (#2D3444), 10% kinetic accents (Electric Cyan #00E5FF, Signal Green #00E676, Voltage Amber #FFB300)",
        default_telemetry="sinusoidal waveform traces, geometric node linkages, and vector coordinate meters",
        accents=["#00E5FF", "#00E676", "#FFB300"],
    ),
    "FINANCE_ECONOMICS": NichePreset(
        name="Finance & Macroeconomics",
        niche_code="FINANCE_ECONOMICS",
        substrate_desc="clean financial analyst slate desk (#F4F5F7) with multi-panel comparative placards",
        palette_desc="Palette: 60% base ground (#F4F5F7), 30% graphite navy (#252C37), 10% kinetic accents (Terminal Amber #FFB300, Bull Green #00E676, Bear Red #EB191E)",
        default_telemetry="proportional ratio blocks, bar distribution meters, and volumetric flow indicators",
        accents=["#FFB300", "#00E676", "#EB191E"],
    ),
    "HISTORY_GEOPOLITICS": NichePreset(
        name="History & Geopolitics",
        niche_code="HISTORY_GEOPOLITICS",
        substrate_desc="archival map research table (#EFECE6) with rolled folios and drafting placards",
        palette_desc="Palette: 60% parchment ground (#EFECE6), 30% sepia charcoal (#3A322D), 10% kinetic accents (Imperial Gold #D4AF37, Deep Navy #1D3557, Terracotta #E07A5F)",
        default_telemetry="non-textual cartographic contour lines, territory boundaries, and tactical vector arrows",
        accents=["#D4AF37", "#1D3557", "#E07A5F"],
    ),
    "PHILOSOPHY_ESSAY": NichePreset(
        name="Philosophy & Visual Essay",
        niche_code="PHILOSOPHY_ESSAY",
        substrate_desc="minimalist conceptual limbo studio (#F0F0F3), clean museum pedestal",
        palette_desc="Palette: 60% base ground (#F0F0F3), 30% neutral slate (#353740), 10% kinetic accents (Solar Gold #F4A261, Lavender Slate #8E9AAF)",
        default_telemetry="geometric thought monuments, proportion balance scales, and radiant vector lines",
        accents=["#F4A261", "#8E9AAF"],
    ),
    "CULTURE_COMEDY": NichePreset(
        name="Cultural Satire & Comedy Explainer",
        niche_code="CULTURE_COMEDY",
        substrate_desc="warm dark mahogany studio workbench (#2A2420), traditional studio ambiance",
        palette_desc="Palette: 60% mahogany ground (#2A2420), 30% charcoal lines (#2D3444), 10% kinetic accents (Amber #FFB300, Mint Green #00E676, Codec-Safe Red #EB191E)",
        default_telemetry="expressive sketch placards and comparative non-textual proportion meters",
        accents=["#FFB300", "#00E676", "#EB191E"],
    ),
}

SPATIAL_LAYOUT_PRESETS: dict[str, str] = {
    "CENTERED_HERO": "centered focal composition strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 920, leaving 10% peripheral bleed padding",
    "LEFT_TO_RIGHT_FLOW": "dynamic directional composition with input catalyst on screen-left (X: 180 to 680), mechanical process in center, and output outcome on screen-right (X: 1240 to 1740)",
    "SPLIT_COMPARATIVE": "split-screen dual composition with bilateral comparative panels on screen-left and screen-right divided by a clean vertical baseline",
    "RULE_OF_THIRDS_LEFT": "asymmetric composition anchored on the left third (X: 200 to 750), balanced by data telemetry in the opposite two-thirds",
    "RULE_OF_THIRDS_RIGHT": "asymmetric composition anchored on the right third (X: 1150 to 1700), balanced by conceptual schematics on the left",
}

TELEMETRY_PRESETS: dict[str, str] = {
    "PROPORTIONAL_RATIO_METERS": "abstract non-textual proportion meters and comparative distribution blocks",
    "NODE_LINKAGE_TOPOLOGY": "geometric node linkages and interconnected coordinate vector pathways",
    "SINUSOIDAL_WAVEFORMS": "fluctuating sinusoidal waveforms and frequency oscillation graphs",
    "TACTICAL_VECTOR_ARROWS": "directional vector arrows, trajectory curves, and territorial contour lines",
    "FLOW_DIAGRAMS": "non-textual schematic flow diagrams with directional pulse indicators",
    "DISTRIBUTION_METERS": "proportional comparative ratio blocks and non-textual scale bars",
}


def get_niche_preset(niche_key: str | None = None) -> NichePreset:
    """Resolves a NichePreset by key with case-insensitive fallback to GENERAL_EXPLAINER."""
    if not niche_key:
        return NICHE_PRESETS["GENERAL_EXPLAINER"]
    key = niche_key.strip().upper().replace(" ", "_").replace("-", "_")
    if key in NICHE_PRESETS:
        return NICHE_PRESETS[key]
    for k, preset in NICHE_PRESETS.items():
        if key in k or k in key:
            return preset
    return NICHE_PRESETS["GENERAL_EXPLAINER"]


def load_channel_profile(run_dir: str | None = None) -> ChannelProfile:
    """Loads channel profile from run directory or returns the default general educational profile."""
    if run_dir:
        candidates = [
            os.path.join(run_dir, "channel_profile.json"),
            os.path.join(run_dir, "channel_config.json"),
        ]
        for c in candidates:
            if os.path.exists(c):
                try:
                    with open(c, encoding="utf-8") as f:
                        data = json.load(f)
                    return ChannelProfile(
                        channel_name=data.get("channel_name", "Automated Explainer Studio"),
                        niche=data.get("niche", "GENERAL_EXPLAINER"),
                        host_mode=data.get("host_mode", "NONE"),
                        host_avatar_description=data.get("host_avatar_description", ""),
                        aspect_ratio=data.get("aspect_ratio", "16:9"),
                        custom_tokens=data.get("custom_tokens", {}),
                    )
                except Exception:
                    pass
    return ChannelProfile(
        channel_name="General Educational Explainer",
        niche="GENERAL_EXPLAINER",
        host_mode="NONE",
        host_avatar_description="",
        aspect_ratio="16:9",
    )
