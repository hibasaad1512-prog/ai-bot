from app.ai.privacy import PrivacyFilter


def test_secret_redaction():
    r = PrivacyFilter.sanitize("email me test@example.com and token=abc123")
    assert r.sensitive
    assert "test@example.com" not in r.text
    assert "abc123" not in r.text


def test_sensitive_topic_redaction():
    r = PrivacyFilter.sanitize("this is a sexual topic")
    assert r.sensitive
    assert r.text == "[REDACTED SENSITIVE TOPIC]"


def test_non_verbatim_does_not_quote():
    r = PrivacyFilter.non_verbatim("hello this is a long original sentence here")
    assert "original sentence" not in r
    assert r.startswith("keywords:")
