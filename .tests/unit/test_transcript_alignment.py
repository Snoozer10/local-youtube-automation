"""Unit tests: transcript alignment & spelling correction (SequenceMatcher path)."""


import correct_transcript_spelling as cts


def _write(path, text, encoding="utf-8"):
    with open(path, "w", encoding=encoding, newline="") as f:
        f.write(text)
    return str(path)


def _read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


class TestTxtAlignment:
    def test_identical_reference_is_identity(self, tmp_path):
        ref = "القمر يدور حول الأرض في مدار ثابت".split()
        src = _write(tmp_path / "t.txt", "[00:00] القمر يدور حول\n[00:05] الأرض في مدار ثابت")
        cts.align_and_correct_file(src, ref, "txt")
        out = _read(src)
        assert "[00:00]" in out and "[00:05]" in out
        assert out.count("الأرض") == 1 and out.count("مدار") == 1

    def test_misspelled_word_replaced_from_reference(self, tmp_path):
        ref = "الكهرباء تتحرك في الأسلاك الموصلة بسرعة عالية جداً هنا".split()
        src = _write(
            tmp_path / "t.txt",
            "[00:00] الكهرباء تتحرك في\n[00:03] الأسلاك الموصلات بسرعة عالية جداً هنا",
        )
        cts.align_and_correct_file(src, ref, "txt")
        out = _read(src)
        assert "الموصلات" not in out.replace("[00:", "").split("[00:")[0]
        assert "الموصلة" in out

    def test_extra_asr_word_is_deleted(self, tmp_path):
        ref = "واحد اثنين تلاتة".split()
        src = _write(tmp_path / "t.txt", "[00:00] واحد اثنين كلمة_شاذة تلاتة")
        cts.align_and_correct_file(src, ref, "txt")
        words = _read(src).replace("[00:00]", "").split()
        assert words == ["واحد", "اثنين", "تلاتة"]

    def test_bom_does_not_break_first_timestamp(self, tmp_path):
        """Repro: txt reader used plain utf-8; a BOM corrupted the first timestamp."""
        ref = "بسم الله الرحمن".split()
        src = _write(tmp_path / "t.txt", "[00:00] بسم الله الرحمن", encoding="utf-8-sig")
        cts.align_and_correct_file(src, ref, "txt")
        first_line = _read(src).splitlines()[0]
        assert first_line.startswith("[00:00]")

    def test_long_transcript_autojunk_keeps_frequent_words(self, tmp_path):
        """Repro: SequenceMatcher autojunk=True corrupts alignment on 200+ word files.

        The frequent token في appears throughout; autojunk treats it as junk,
        redistributing it into wrong timestamp groups.
        """
        base = []
        for i in range(60):
            base.extend(["في", "الوسط", f"و{i}"])
        ref = list(base)
        trans = list(base)
        trans[10] = "وسَط"  # single rare misspelling
        lines = []
        for start in range(0, len(trans), 6):
            chunk = trans[start:start + 6]
            mm, ss = divmod(start, 60)
            lines.append(f"[{mm:02d}:{ss:02d}] " + " ".join(chunk))
        src = _write(tmp_path / "long.txt", "\n".join(lines) + "\n")

        cts.align_and_correct_file(src, ref, "txt")
        body_words = [
            w
            for line in _read(src).splitlines()
            for w in line.replace("[", "").split("] ")[-1].split()
            if line.strip()
        ]
        # Every reference word must survive exactly once — no duplication/drop.
        assert body_words == ref, (
            f"drift: {sum(1 for a, b in zip(body_words, ref, strict=False) if a != b)} mismatched positions"
        )

    def test_empty_transcript_file_does_not_crash(self, tmp_path):
        src = _write(tmp_path / "empty.txt", "")
        cts.align_and_correct_file(src, [], "txt")  # must not raise IndexError
        assert _read(src) == "" or _read(src) == "\n"

    def test_write_is_atomic_leaves_no_tmp(self, tmp_path):
        ref = "نص قصير واضح".split()
        src = _write(tmp_path / "t.txt", "[00:00] نص قصير واضح")
        cts.align_and_correct_file(src, ref, "txt")
        assert not list(tmp_path.glob("*.tmp"))


class TestSrtAlignment:
    def _sample_srt(self):
        return (
            "1\n00:00:00,000 --> 00:00:02,000\nواحد اثنين\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\nتلاتة أربعة\n"
        )

    def test_blocks_and_numbering_preserved(self, tmp_path):
        ref = "واحد اثنين تلاتة أربعة".split()
        src = _write(tmp_path / "s.srt", self._sample_srt())
        cts.align_and_correct_file(src, ref, "srt")
        out = _read(src)
        assert out.startswith("1\n")
        assert "00:00:00,000 --> 00:00:02,000" in out
        assert "00:00:02,000 --> 00:00:04,000" in out
        assert "واحد اثنين" in out and "تلاتة أربعة" in out

    def test_correction_lands_in_right_block(self, tmp_path):
        ref = "واحد اتنين تلاتة أربعة".split()
        src = _write(tmp_path / "s.srt", self._sample_srt().replace("اثنين", "اثنينٍ"))
        cts.align_and_correct_file(src, ref, "srt")
        out = _read(src)
        assert "اتنين" in out.split("\n\n")[0]

    def test_malformed_block_skipped_without_corruption(self, tmp_path):
        srt = "1\n00:00:00,000 --> 00:00:01,000\nواحد\n\nX\nbroken block only\n"
        ref = "خمسة ستة سبعة".split()
        src = _write(tmp_path / "s.srt", srt)
        cts.align_and_correct_file(src, ref, "srt")  # must not raise
        assert "broken block only" in _read(src)
