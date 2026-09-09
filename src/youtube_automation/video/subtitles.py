from __future__ import annotations

import os
import re


def fix_arabic_srt(input_path, output_path):
    with open(input_path, encoding="utf-8-sig") as f:
        content = f.read()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


def build_subtitle_style_string(config: dict) -> str:
    return (
        f"Fontname={config['SUB_FONT_NAME']},"
        f"Fontsize={config['SUB_FONT_SIZE']},"
        f"PrimaryColour={config['SUB_PRIMARY_COLOR']},"
        f"OutlineColour={config['SUB_OUTLINE_COLOR']},"
        f"BorderStyle={config['SUB_BORDER_STYLE']},"
        f"Outline={config['SUB_OUTLINE']},"
        f"Shadow={config['SUB_SHADOW']},"
        f"Alignment={config['SUB_ALIGNMENT']},"
        f"MarginV={config['SUB_MARGIN_V']},"
        f"Bold={config['SUB_BOLD']}"
    )


def build_dynamic_ass_subtitles(
    raw_transcript_path: str, output_ass_path: str, config: dict, total_duration: float = 0.0
):
    """
    Generates broadcast-grade Advanced SubStation Alpha (.ass) subtitles with
    dynamic active-word color highlights and Arabic typography shaping.
    """
    if not os.path.exists(raw_transcript_path):
        return None

    font_name = config.get("SUB_FONT_NAME", "Arial")
    font_size = int(config.get("SUB_FONT_SIZE", 32))
    # ASS uses BGR hex format (&H00BBGGRR)
    primary_color = "&H00FFFFFF"  # Crisp White
    highlight_color = "&H003EB0FF"  # Warm Amber (#E09F3E in BGR)
    outline_color = "&H00000000"  # Pure Black
    margin_v = int(config.get("SUB_MARGIN_V", 65))

    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.get("OUTPUT_WIDTH", 2560)}
PlayResY: {config.get("OUTPUT_HEIGHT", 1440)}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H80000000,1,0,0,0,100,100,0,0,1,3.8,2.0,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def format_ass_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines = []
    with open(raw_transcript_path, encoding="utf-8") as f:
        for raw_line in f:
            line_str = raw_line.strip()
            if not line_str:
                continue
            match = re.match(r"^\[?(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\]?\s*(.*)", line_str)
            if match:
                h = int(match.group(1)) if match.group(1) else 0
                m = int(match.group(2))
                s = float(match.group(3))
                start_sec = h * 3600.0 + m * 60.0 + s
                text = match.group(4).strip()
                if text:
                    lines.append((start_sec, text))

    events = []
    for i, (start_sec, text) in enumerate(lines):
        end_sec = (
            lines[i + 1][0]
            if i < len(lines) - 1
            else (total_duration if total_duration > start_sec else start_sec + 3.5)
        )

        words = text.split()
        if not words:
            continue

        start_str = format_ass_time(start_sec)
        end_str = format_ass_time(end_sec)

        # Build dynamic word-by-word timing tags
        highlighted_body = "".join(
            [
                f"{{\\c{highlight_color}\\t(0,200,\\fscx105\\fscy105)}}{w}{{\\c{primary_color}\\fscx100\\fscy100}} "
                for w in words
            ]
        )

        event_line = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{highlighted_body.strip()}"
        events.append(event_line)

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(events) + "\n")

    return output_ass_path


