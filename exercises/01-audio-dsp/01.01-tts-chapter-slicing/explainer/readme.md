# Explainer: Neural TTS Chapter Slicing & Sequence Invariants

## 1. The Speech Tag Armor Pattern
Modern neural voice synthesizers (such as Gemini 2.5 Pro TTS preview in Google AI Studio) accept bracketed prosody directives to modulate pitch, speed, and emotion:
- `[tone: energetic]`
- `[pace: slow]`
- `[pause: 1.2s]`

However, LLMs routinely output capitalized or title-cased directives:
```text
[Tone: Serious]
[PAUSE: 2.0s]
```
When submitted to AI Studio without sanitization, the TTS speech tokenizer fails to match the directive dictionary and treats the tokens as literal English text. The resulting audio awkwardly enunciates: *"Bracket capital T-O-N-E colon Serious bracket"*.

**The Armor Rule:**
All occurrences of `[(tone|pace|pause): ...]` must be normalized to lowercase prior to audio generation:
```python
def lowercase_tts_tags(match):
    return match.group(0).lower()

text = re.sub(r"\[(tone|pace|pause)\s*:[^\]]+\]", lowercase_tts_tags, text, flags=re.IGNORECASE)
```

## 2. Terminal Trigger Word Stripping
Gemini script refinement prompts often conclude with operational prompts such as:
- `PROCEED`
- `COMPLETE`
- `FINISHED`
- `READY`

If these control words leak into the TTS input, the voice synthesizer will speak them at the end of every chapter. Slicing logic must discard lines containing standalone control keywords.

## 3. Contiguous Sequencing & Gap Detection
A failure during chapter generation (e.g. timeout on Chapter 3 of 10) leaves a hole in the sequence:
```
Chapter_1.wav  (Present)
Chapter_2.wav  (Present)
Chapter_3.wav  (MISSING!)
Chapter_4.wav  (Present - Orphan)
```
If blind concatenation were applied, Chapter 4 would immediately follow Chapter 2, introducing severe narrative desynchronization. The sequence detector must isolate:
1. Contiguous prefix: chapters `[1, 2]` can proceed or be safely reviewed.
2. Missing list: chapter `3` must be rescheduled for generation.
3. Orphan list: chapter `4` is present but must NOT be stitched until chapter `3` is restored.
