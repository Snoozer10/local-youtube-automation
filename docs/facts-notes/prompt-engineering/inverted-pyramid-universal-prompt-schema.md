# Knowledge Note: Inverted Pyramid Universal Prompt Schema

## 1. The Token Attention Problem in Text-to-Image Models
Modern diffusion and autoregressive text-to-image models (such as Imagen 3 / Imagen 4 used in Google Flow) distribute cross-attention weights disproportionately across the prompt. Empirical analysis reveals that the **first 30–50 tokens** receive the highest attentional weight.

In classical prompt templates, extensive style boilerplate and negative constraints were placed at the beginning:
```text
[High-end 2D graphic vector animation explainer style, uniform 3px deep charcoal linework, flat 2-step cel-shading...]
[Orthographic flat 2D projection plane...]
[Clean 16:9 widescreen composition strictly bounded inside coordinates X: 180 to 1740...]
[Locked studio substrate...]
[Subject: canine brain anatomical structure] <- Squeezed at token 55!
```
Placing the subject and action at Token 55+ caused **semantic attenuation**: the model spent its primary cross-attention budget rendering the generic vector style, while the specific subject details suffered loss of fidelity or were misrendered.

---

## 2. The Inverted Pyramid 4-Zone Grammar Standard

The Inverted Pyramid prompt grammar standard reorganizes the prompt into 4 distinct token zones ordered by attentional priority:

```
┌────────────────────────────────────────────────────────────────────────┐
│ ZONE 1: PRIMARY SEMANTIC ENTITY & ACTION (Tokens 1 - 35)               │
│ -> Framing Scale + Core Subject Noun + Dynamic Physical Action         │
├────────────────────────────────────────────────────────────────────────┤
│ ZONE 2: SPATIAL STAGING & TELEMETRY (Tokens 36 - 55)                   │
│ -> 16:9 Staging Rule + Non-Linguistic Telemetry Archetype              │
├────────────────────────────────────────────────────────────────────────┤
│ ZONE 3: NICHE SUBSTRATE GROUND & PALETTE (Tokens 56 - 75)              │
│ -> Domain-Specific Desk/Substrate + 60-30-10 Chromatic Distribution    │
├────────────────────────────────────────────────────────────────────────┤
│ ZONE 4: MASTER STYLE ANCHOR & QUALITY BANS (Tokens 76 - 95)            │
│ -> 2D Vector Cel-Shading + Negative Prohibition Enforcement            │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Concrete Grammar Example

### Mode A Master Setup:
```text
Medium shot (MS) framing of canine brain anatomical structure, neural pathways illuminated with glowing coordinate nodes. Framed on the left third (X: 180 to 750), connected by vector lines to comparative proportion meters on the right. Locked substrate, neutral light studio limbo desk (#F8F8FA), clean orthographic 2D projection plane. Palette: 60% base ground, 30% charcoal lines, 10% kinetic accents (Cyan #00E5FF, Amber #FFB300, Spring Green #00E676, Codec-Safe Red #EB191E). 2D graphic vector animation explainer style, crisp 3px deep charcoal (#2D3444) contour linework, flat 2-step cel-shading, zero gradients, zero text.
```

### Mode B Progressive Surgical Delta (L.A.D. Formula):
```text
In the attached reference image, maintain identical subject and background. Add expanding vector signal lines radiating from the brain nodes toward a human figure.
```
- Total word count: 23 words (<25 word hard ceiling).
- Zero style DNA, zero camera specifications, zero negative prompt clutter.
- Relies 100% on the attached reference card chip in Google Flow.
