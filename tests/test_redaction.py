from app.security.redaction import redact_text


def test_redact_text_masks_email_phone_and_numbers():
    s = "Напишите на test@example.com или позвоните +7 999 123-45-67. Номер: 1234567890123"
    out = redact_text(s)
    assert "[EMAIL]" in out
    assert "[PHONE]" in out
    assert "[ACCOUNT]" in out

