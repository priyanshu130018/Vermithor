import re
from backend.app.log_intelligence.parsing.normalizer import LogNormalizer


class LogTemplateExtractor:
    """Extracts generalized and reusable log templates from normalized text."""

    @classmethod
    def extract_template(cls, raw_or_normalized_message: str) -> str:
        """
        Produce a reusable template pattern from log text.

        Returns:
            str: General log template.
        """
        # Ensure log has passed normalization
        normalized = LogNormalizer.normalize_log(raw_or_normalized_message)

        # Further collapse repeated variable tokens (e.g. `<NUM> <NUM>` -> `<NUM>`)
        template = re.sub(r"(<NUM>\s*)+", "<NUM> ", normalized)
        template = re.sub(r"(<HEX>\s*)+", "<HEX> ", template)
        template = re.sub(r"\s+", " ", template).strip()
        return template
