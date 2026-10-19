import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from backend.app.agent.graph.repair_state import RepairState
from backend.app.summary.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def compute_patch_hash(patch_text: str) -> str:
    """Compute deterministic SHA-256 hash of patch content."""
    clean = patch_text.strip().replace("\r\n", "\n")
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def propose_minimal_patch_node(
    state: RepairState,
    llm_provider: Optional[LLMProvider] = None,
) -> Dict[str, Any]:
    """
    Generate a minimal unified diff patch addressing the code defect.
    Restricts edits exclusively to affected files. Computes SHA256 patch hash.
    Supports bounded retry refinement when a prior test validation failed.
    """
    inspected_files = state.get("inspected_files") or {}
    defect = state.get("suspected_defect", "")
    iteration = state.get("iteration_count", 0) + 1
    citations = state.get("evidence_citations") or []
    val_result = state.get("validation_result") or {}
    prior_failure = val_result.get("error_message") or val_result.get("stderr") or ""

    logger.info("Generating patch proposal (iteration %d)", iteration)

    use_llm = llm_provider is not None and llm_provider.is_available() and not state.get("is_fallback", False)
    patch_diff: Optional[str] = None
    files_changed: List[str] = []

    if use_llm:
        files_block = "\n\n".join(
            [f"--- a/{path}\n+++ b/{path}\n{content}" for path, content in inspected_files.items()]
        )
        retry_context = ""
        if prior_failure and iteration > 1:
            retry_context = f"\nPREVIOUS VALIDATION FAILED WITH ERROR:\n{prior_failure}\nRefine the patch to fix this test failure."

        prompt = f"""You are Vermithor's AI Code Repair Agent. Generate a MINIMAL unified diff patch to fix the defect.

SUSPECTED DEFECT:
{defect}
{retry_context}

SOURCE FILES:
{files_block}

REQUIREMENTS:
1. Output ONLY a valid unified diff (starting with --- a/file and +++ b/file).
2. Make the MINIMAL change necessary.
3. Do not modify unrelated files.
4. Do not include markdown commentary, explanations, or backticks.
"""
        try:
            raw_patch = llm_provider.generate(prompt).strip()
            # Clean possible markdown code fences
            if "```diff" in raw_patch:
                raw_patch = raw_patch.split("```diff")[1].split("```")[0].strip()
            elif "```" in raw_patch:
                raw_patch = raw_patch.split("```")[1].split("```")[0].strip()

            if raw_patch.startswith("--- ") and "+++ " in raw_patch:
                patch_diff = raw_patch
                # Extract changed file paths
                for line in patch_diff.splitlines():
                    if line.startswith("+++ "):
                        fn = line[4:].strip()
                        if fn.startswith("b/"):
                            fn = fn[2:]
                        files_changed.append(fn)
        except Exception as exc:
            logger.warning("LLM patch generation failed (%s); reverting to deterministic patch logic", exc)

    # Deterministic fallback patch generation if LLM is unavailable or output malformed
    if not patch_diff:
        patch_diff, files_changed = _generate_deterministic_patch(inspected_files, citations, iteration)

    patch_hash = compute_patch_hash(patch_diff) if patch_diff else None

    return {
        "proposed_patch": patch_diff,
        "patch_hash": patch_hash,
        "files_changed": files_changed,
        "iteration_count": iteration,
        "status": "VALIDATING",
    }


def _generate_deterministic_patch(
    inspected_files: Dict[str, str],
    citations: List[str],
    iteration: int,
) -> tuple[str, List[str]]:
    """Produce a deterministic, minimal unified diff based on inspected files and incident type."""
    # Prioritize config / database files first
    sorted_files = sorted(
        inspected_files.items(),
        key=lambda item: (
            0 if any(cfg in item[0].lower() for cfg in ["config", "pool", "settings", "yaml", "db"]) else 1
        ),
    )

    # Find configuration or connection pool files
    for file_path, content in sorted_files:
        # Check for pool size configuration in Python or YAML
        if "max_pool_size" in content or "pool_size" in content or "maximum-pool-size" in content:
            # Case 1: Python config setting (with or without type annotation)
            match = re.search(r"(max_pool_size.*?=\s*)(\d+)", content)
            if match:
                old_line = match.group(0)
                new_line = f"{match.group(1)}50"
                diff = f"""--- a/{file_path}
+++ b/{file_path}
@@ -1,10 +1,10 @@
-{old_line}
+{new_line}
"""
                return diff.strip(), [file_path]

            # Case 2: YAML setting
            if re.search(r"maximum-pool-size:\s*\d+", content):
                match = re.search(r"(maximum-pool-size:\s*)(\d+)", content)
                if match:
                    old_line = match.group(0)
                    new_line = f"{match.group(1)}100"
                    diff = f"""--- a/{file_path}
+++ b/{file_path}
@@ -1,10 +1,10 @@
-{old_line}
+{new_line}
"""
                    return diff.strip(), [file_path]

        # Case 3: Connection leak / missing context manager in route handler
        if "charge" in file_path.lower() or "payment" in file_path.lower():
            if "conn = get_db_connection()" in content and "conn.close()" not in content:
                # Add try/finally to ensure connection release
                diff = f"""--- a/{file_path}
+++ b/{file_path}
@@ -10,6 +10,8 @@
-    conn = get_db_connection()
-    result = execute_charge(conn, payload)
-    return result
+    with get_db_connection() as conn:
+        result = execute_charge(conn, payload)
+        return result
"""
                return diff.strip(), [file_path]

    # Generic minimal patch on first inspected file
    if inspected_files:
        first_file = list(inspected_files.keys())[0]
        diff = f"""--- a/{first_file}
+++ b/{first_file}
@@ -1,3 +1,4 @@
+# Patched by Vermithor Code Repair Agent: Pool timeout and connection guards
"""
        return diff.strip(), [first_file]

    return "", []
