from refine_script import DialectTashkeelEngine


def test_dialect_tashkeel_engine_vocalizes_arabic_words():
    # Force fresh instance
    engine = DialectTashkeelEngine()
    engine._initialize()
    raw_text = 'ده بيقول كده يا معلم دي سحلة وخازوق في قسط'
    transformed = engine.transform(raw_text)
    assert 'كِدَه' in transformed
    assert 'بِيُقول' in transformed
    assert 'مِعَلّم' in transformed
    assert 'سَحْلَة' in transformed
    assert 'خَازُوق' in transformed
    assert 'قِسط' in transformed
