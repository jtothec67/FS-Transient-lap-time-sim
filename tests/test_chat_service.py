import json
from pathlib import Path

from app.services.chat_service import _read_key, _load_index, _load_section_content


def test_read_key(tmp_path):
    key_file = tmp_path / "deepseek_key"
    key_file.write_text("sk-test-key-abc\n", encoding="utf-8")
    assert _read_key(key_file) == "sk-test-key-abc"


def test_load_index_returns_required_fields(tmp_path):
    index = [{"file": "Tyre-Model.md", "section": "Where base_mu fits", "summary": "A summary.", "heading_level": 2}]
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    result = _load_index(index_path)
    assert isinstance(result, list)
    assert result[0]["file"] == "Tyre-Model.md"
    assert result[0]["section"] == "Where base_mu fits"


def test_load_section_content_returns_nonempty_text():
    content = _load_section_content("Tyre-Model.md", "Where base_mu fits")
    assert "base_mu" in content
    assert len(content) > 20
