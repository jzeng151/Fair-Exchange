"""Streamed text: messages said back to back in one turn must not run together (#126)."""
from fex.conversation import copy
from fex.conversation.engine import _Turn


def text_of(turn: _Turn) -> str:
    return "".join(e.text for e in turn.events if e.type == "text")


def test_two_messages_in_one_turn_are_separated_by_a_space():
    turn = _Turn()
    turn.say(copy.text("en", "no_peers"))
    turn.say(copy.text("en", "hand_back"))
    assert "yet. This is information" in text_of(turn)


def test_every_language_keeps_the_space():
    for lang in ("en", "es", "fr"):
        turn = _Turn()
        turn.say(copy.text(lang, "no_peers"))
        turn.say(copy.text(lang, "hand_back"))
        first, second = copy.text(lang, "no_peers"), copy.text(lang, "hand_back")
        assert text_of(turn) == f"{first} {second}"


def test_a_single_message_streams_unchanged():
    turn = _Turn()
    turn.say("Hola, ¿cómo está?")
    assert text_of(turn) == "Hola, ¿cómo está?"
    assert turn.spoken == ["Hola, ¿cómo está?"]
