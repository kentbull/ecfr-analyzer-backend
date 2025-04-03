import ecfr.services
from ecfr import endpoints


def test_word_counter():
    xml_text = "<root><p>Hello <b>world</b> again</p></root>"
    count = ecfr.services.word_count(xml_text)
    assert 3 == count
