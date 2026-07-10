"""Secret and sensitive-file redaction."""

from beachops.services.redaction import REDACTED, is_sensitive_path, redact_text, redact_value


def test_redacts_assignments_bearer_tokens_and_url_passwords() -> None:
    source = (
        "API_KEY=super-secret-value\n"
        'Authorization: Bearer abc.def.ghi\n'
        "DATABASE_URL=postgresql://bot:plain-password@db/beachops"
    )

    result = redact_text(source)

    assert "super-secret-value" not in result
    assert "abc.def.ghi" not in result
    assert "plain-password" not in result
    assert result.count(REDACTED) >= 3


def test_redacts_sensitive_mapping_values_recursively() -> None:
    result = redact_value({"github_token": "secret", "nested": {"password": "pw"}})

    assert result == {
        "github_token": REDACTED,
        "nested": {"password": REDACTED},
    }


def test_detects_sensitive_files_across_platform_paths() -> None:
    assert is_sensitive_path(r"C:\repo\.env")
    assert is_sensitive_path("/home/app/.ssh/id_ed25519")
    assert is_sensitive_path("certificates/client.pem")
    assert not is_sensitive_path("src/settings.py")

