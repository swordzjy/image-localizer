import os

from image_localizer.env import find_dotenv, load_dotenv, parse_dotenv


def test_parse_dotenv_handles_comments_quotes_and_export():
    text = "\n".join(
        [
            "# a comment",
            "",
            "ANTHROPIC_MODEL=claude-sonnet-5",
            'ANTHROPIC_API_KEY="sk-secret"',
            "export OPENAI_API_KEY='oa-secret'",
            "NO_VALUE_LINE_WITHOUT_EQUALS",
        ]
    )
    parsed = parse_dotenv(text)
    assert parsed == {
        "ANTHROPIC_MODEL": "claude-sonnet-5",
        "ANTHROPIC_API_KEY": "sk-secret",
        "OPENAI_API_KEY": "oa-secret",
    }


def test_load_dotenv_populates_environ(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("MY_TEST_KEY=hello\n", encoding="utf-8")
    monkeypatch.delenv("MY_TEST_KEY", raising=False)

    applied = load_dotenv(env_file)

    assert applied == {"MY_TEST_KEY": "hello"}
    assert os.environ["MY_TEST_KEY"] == "hello"


def test_existing_environment_takes_precedence(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("MY_TEST_KEY=from_file\n", encoding="utf-8")
    monkeypatch.setenv("MY_TEST_KEY", "from_shell")

    load_dotenv(env_file)

    assert os.environ["MY_TEST_KEY"] == "from_shell"


def test_find_dotenv_searches_parent_directories(tmp_path):
    (tmp_path / ".env").write_text("K=V\n", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    assert find_dotenv(nested) == tmp_path / ".env"
