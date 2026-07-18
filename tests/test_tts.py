from __future__ import annotations

import pytest

from yel import tts
from yel.errors import TTSError


INVENTORY = """\
Samantha            en_US    # Hello! My name is Samantha.
Mónica              es_ES    # ¡Hola! Me llamo Mónica.
Thomas              fr_FR    # Bonjour, je m’appelle Thomas.
Eddy (German (Germany)) de_DE    # Hallo! Ich heiße Eddy.
"""


def test_parse_voices_and_locale_matched_selection():
    voices = tts.parse_voices(INVENTORY)

    assert voices == {
        "Samantha": "en_US",
        "Mónica": "es_ES",
        "Thomas": "fr_FR",
        "Eddy (German (Germany))": "de_DE",
    }
    assert tts.voice_for_language(voices=voices) == ("Samantha", "en_US")
    assert tts.voice_for_language("en-US", voices=voices) == ("Samantha", "en_US")
    assert tts.voice_for_language("es", voices=voices) == ("Mónica", "es_ES")
    assert tts.voice_for_language("fr", voices=voices) == ("Thomas", "fr_FR")
    assert tts.voice_for_language("de", voices=voices) == ("Eddy (German (Germany))", "de_DE")
    assert tts.VOICE_GENDER_BY_LOCALE["de_DE"] == "male"


def test_voice_selection_rejects_wrong_or_unsupported_locale():
    with pytest.raises(TTSError, match="must be installed as es_ES"):
        tts.voice_for_language("es", voices={"Mónica": "en_US"})
    with pytest.raises(TTSError, match="Unsupported TTS language"):
        tts.voice_for_language("it", voices=tts.parse_voices(INVENTORY))
