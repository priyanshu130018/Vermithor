from backend.app.log_intelligence.parsing.template_extractor import LogTemplateExtractor


def test_template_extraction_identical_patterns():
    """Verify that different IP/port/session instances of the same error produce identical templates."""
    log_a = "Connection refused to postgres at 10.20.30.41:5432 session 11111111-1111-1111-1111-111111111111"
    log_b = "Connection refused to postgres at 10.20.30.52:5432 session 22222222-2222-2222-2222-222222222222"

    tpl_a = LogTemplateExtractor.extract_template(log_a)
    tpl_b = LogTemplateExtractor.extract_template(log_b)

    assert tpl_a == tpl_b
    assert "Connection refused to postgres at <IP>:<PORT> session <UUID>" == tpl_a


def test_template_extraction_distinct_patterns():
    """Verify that semantically distinct log messages produce distinct templates."""
    log_a = "Connection refused to postgres at 10.20.30.41:5432"
    log_b = "User authentication failed for user alice from 192.168.1.10"

    tpl_a = LogTemplateExtractor.extract_template(log_a)
    tpl_b = LogTemplateExtractor.extract_template(log_b)

    assert tpl_a != tpl_b
