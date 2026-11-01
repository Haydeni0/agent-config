"""Codec contract: parse/render round-trips and invalid-input failure (seam C)."""

import pytest

from settings_sync.merging import JsonCodec, TomlCodec, YamlCodec, canonicalize, codec_by_name


def test_json_codec_round_trips_and_renders_two_space():
    codec = JsonCodec()
    assert codec.loads('{"a": 1}\n') == {"a": 1}
    assert codec.dumps({"a": 1}) == '{\n  "a": 1\n}\n'
    with pytest.raises(ValueError):
        codec.loads("{broken")


def test_yaml_codec_round_trips_preserving_key_order():
    codec = YamlCodec()
    assert codec.loads("b: 2\na: 1\n") == {"b": 2, "a": 1}
    assert codec.dumps({"b": 2, "a": 1}) == "b: 2\na: 1\n"
    with pytest.raises(ValueError):
        codec.loads("a: [unclosed\n")


def test_toml_codec_keeps_formatting_and_comments():
    codec = TomlCodec()
    original = "# Local preferences\nmodel = 'example-model'\n[features]\nhooks=true\ncustom_flag=true\n"
    doc = codec.loads(original)
    assert codec.dumps(doc) == original  # untouched document re-renders verbatim
    doc["model"] = "new"
    rendered = codec.dumps(doc)
    assert "# Local preferences" in rendered   # S69: trivia survives a real merge
    assert "hooks=true" in rendered
    assert codec.loads(rendered)["model"] == "new"
    assert codec.loads(rendered)["features"] == {"hooks": True, "custom_flag": True}
    with pytest.raises(ValueError):
        codec.loads("model = 'unterminated\n")


def test_canonicalize_maps_datetimes_to_iso_strings():
    import datetime
    stamp = datetime.datetime(2026, 10, 31, 12, 0, 0)
    assert canonicalize({"t": stamp, "n": [1, {"d": stamp.date()}]}) == {
        "t": "2026-10-31T12:00:00", "n": [1, {"d": "2026-10-31"}]
    }
    assert canonicalize("plain") == "plain"


def test_codec_by_name_and_unknown():
    assert codec_by_name("json").name == "json"
    assert codec_by_name("toml").name == "toml"
    with pytest.raises(ValueError):
        codec_by_name("xml")
