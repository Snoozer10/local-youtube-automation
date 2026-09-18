# Knowledge Note: Dynamic Niche & Channel Adaptation System

## 1. Context & Motivation
Earlier iterations of the YouTube Automation pipeline hardcoded Egyptian colloquial persona elements (`Al-Daheeh`, `Abo Hmeed`, `Ahwa cafe`, `tea cup`) directly into low-level prompt enhancers and fallback handlers. While effective for that specific series, this created tight architectural coupling, preventing the pipeline from generating content for other channels, genres, and educational niches.

The Dynamic Niche Adaptation System completely decouples:
1. **Niche & Domain Environment** (`NICHE_PRESETS`)
2. **Channel Identity & Host Persona** (`ChannelProfile`)
3. **Chromatic Attention Palette** (Adaptive 60-30-10 distribution)
4. **Abstract Telemetry Archetype** (Non-linguistic data visuals)

---

## 2. Architecture & Registry

### 2.1 The Niche Profile Schema
```json
{
  "channel_id": "string",
  "channel_name": "string",
  "niche": "SCIENCE_TECH | FINANCE_ECONOMICS | HISTORY_GEOPOLITICS | PHILOSOPHY_ESSAY | GENERAL_EXPLAINER | CULTURE_COMEDY",
  "host_mode": "NONE | CUSTOM_AVATAR | DOCUMENTARY_OBSERVER",
  "host_avatar_description": "string (optional visual description of narrator)",
  "aspect_ratio": "16:9",
  "default_substrate": "LIGHT_LIMBO | DARK_TERMINAL | OAK_ARCHIVE | SLATE_DESK",
  "primary_accents": ["#HEX1", "#HEX2", "#HEX3"]
}
```

### 2.2 Standard Niche Registries

| Niche Code | Substrate Ground (60%) | Linework (30%) | Kinetic Accents (10%) | Primary Telemetry Archetype |
| :--- | :--- | :--- | :--- | :--- |
| `SCIENCE_TECH` | Neutral Light Limbo (`#F8F8FA`) / Dark Terminal (`#14161D`) | Deep Charcoal (`#2D3444`) | Electric Cyan (`#00E5FF`), Signal Green (`#00E676`) | `NODE_LINKAGE_TOPOLOGY`, `SINUSOIDAL_WAVEFORMS` |
| `FINANCE_ECONOMICS` | Financial Slate Desk (`#F4F5F7`) | Graphite Navy (`#252C37`) | Terminal Amber (`#FFB300`), Bull Green (`#00E676`), Bear Red (`#EB191E`) | `PROPORTIONAL_RATIO_BLOCKS`, `DISTRIBUTION_METERS` |
| `HISTORY_GEOPOLITICS` | Archival Oak Table (`#EFECE6`) | Sepia Charcoal (`#3A322D`) | Imperial Gold (`#D4AF37`), Deep Navy (`#1D3557`), Terracotta (`#E07A5F`) | `CARTOGRAPHIC_CONTOURS`, `TACTICAL_VECTOR_ARROWS` |
| `PHILOSOPHY_ESSAY` | Minimalist Chiaroscuro Void (`#16161A`) | Neutral Slate (`#353740`) | Solar Gold (`#F4A261`), Lavender Slate (`#8E9AAF`) | `GEOMETRIC_MONUMENTS`, `PROPORTIONAL_SCALES` |
| `GENERAL_EXPLAINER` | Neutral Studio Desk (`#F8F8FA`) | Deep Charcoal (`#2D3444`) | Balanced Spectrum (`#00E5FF`, `#FFB300`, `#00E676`, `#EB191E`) | `PROPORTIONAL_RATIO_METERS`, `FLOW_DIAGRAMS` |

---

## 3. Host Modularity & Fallback
- When `host_mode == "NONE"` (e.g. Kurzgesagt / Wendover style):
  Prompts feature pure apparatus diagrams, physical drafting placards, isometric setups, and environmental objects without injecting human figures.
- When `host_mode == "CUSTOM_AVATAR"`:
  `CHARACTER_HOST_MAIN` expands dynamically into the avatar visual DNA declared in the active `ChannelProfile`.
- Hardcoded fallback strings like `"Al-Daheeh cartoon host..."` are completely eliminated from `flow_generator.py` and `prompt_enhancer.py`.
