"""JSONC loader tests."""

from __future__ import annotations

import json

import pytest

from bellman.attributes import loads_jsonc, strip_jsonc


def test_line_and_block_comments() -> None:
    text = """{
      // line comment
      "a": 1, /* inline */ "b": [1, /* mid */ 2]
      /* multi
         line */
    }"""
    assert loads_jsonc(text) == {"a": 1, "b": [1, 2]}


def test_trailing_commas_in_objects_and_arrays() -> None:
    text = '{"a": [1, 2,], "b": {"c": 3,},}'
    assert loads_jsonc(text) == {"a": [1, 2], "b": {"c": 3}}


def test_trailing_comma_before_comment_then_close() -> None:
    text = '{"a": 1, // note\n}'
    assert loads_jsonc(text) == {"a": 1}


def test_slashes_inside_strings_are_preserved() -> None:
    text = '{"url": "https://example.com/a//b", "c": "/* not a comment */"}'
    assert loads_jsonc(text) == {
        "url": "https://example.com/a//b",
        "c": "/* not a comment */",
    }


def test_escaped_quote_does_not_end_string() -> None:
    text = r'{"a": "say \"hi\" // still string", "b": 2}'
    assert loads_jsonc(text) == {"a": 'say "hi" // still string', "b": 2}


def test_comma_inside_string_before_brace_is_preserved() -> None:
    assert loads_jsonc('{"a": "x,}"}') == {"a": "x,}"}


def test_unterminated_block_comment() -> None:
    with pytest.raises(ValueError, match="unterminated block comment"):
        strip_jsonc('{"a": 1} /* never closed')


def test_invalid_json_is_value_error_with_original_line() -> None:
    text = '{\n  // comment\n  /* block\n  spans */\n  "a": oops\n}'
    with pytest.raises(json.JSONDecodeError) as excinfo:
        loads_jsonc(text)
    assert excinfo.value.lineno == 5


def test_strip_returns_plain_json() -> None:
    assert json.loads(strip_jsonc('{"a": 1, // x\n}')) == {"a": 1}
