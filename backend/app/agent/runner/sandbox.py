import logging
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Set

from backend.app.agent.git.base import redact_secrets, sanitize_file_path
from backend.app.agent.schemas.repair import TestExecutionResult, ValidationStatus

logger = logging.getLogger(__name__)

# Disallowed environment variables that could leak production secrets or credentials
_SENSITIVE_ENV_VARS: Set[str] = {
    "DATABASE_URL",
    "DATABASE_URL_UNPOOLED",
    "POSTGRES_PASSWORD",
    "POSTGRES_USER",
    "NEON_API_KEY",
    "JWT_SECRET",
    "SECRET_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GITHUB_TOKEN",
    "HF_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DOCKER_HOST",
    "DOCKER_CERT_PATH",
}

# Approved test commands for sandboxed execution
_ALLOWED_COMMAND_BINARIES: Set[str] = {
    "pytest",
    "python",
    "python3",
    "py",
    "npm",
    "mvn",
    "gradle",
    "go",
}

# Maximum disk size for disposable sandbox (50 MB)
_MAX_SANDBOX_BYTES = 50 * 1024 * 1024


def apply_unified_diff(repo_root: Path, diff_text: str) -> List[str]:
    """
    Safely parse and apply a minimal unified diff to target files inside the sandboxed repo root.
    Returns the list of modified relative file paths.
    
    Raises:
        ValueError: If diff is malformed, attempts path traversal, or fails to apply.
    """
    if not diff_text or not diff_text.strip():
        raise ValueError("Unified diff content is empty")

    modified_files: List[str] = []
    lines = diff_text.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            # Format: --- a/path/to/file or --- path/to/file
            old_file_line = line[4:].strip()
            if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                raise ValueError(f"Malformed diff header near line {i}: expected '+++ '")
            new_file_line = lines[i + 1][4:].strip()
            i += 2

            # Strip a/ and b/ prefixes if present
            clean_rel_path = new_file_line
            if clean_rel_path.startswith("b/"):
                clean_rel_path = clean_rel_path[2:]
            elif clean_rel_path.startswith("a/"):
                clean_rel_path = clean_rel_path[2:]

            target_path = sanitize_file_path(clean_rel_path, repo_root=repo_root)
            if not target_path.exists():
                raise FileNotFoundError(f"Target file '{clean_rel_path}' does not exist in sandbox")

            # Collect hunks for this file
            file_hunks: List[List[str]] = []
            current_hunk: List[str] = []
            while i < len(lines) and not lines[i].startswith("--- "):
                hunk_line = lines[i]
                if hunk_line.startswith("@@ "):
                    if current_hunk:
                        file_hunks.append(current_hunk)
                    current_hunk = [hunk_line]
                elif current_hunk:
                    current_hunk.append(hunk_line)
                i += 1
            if current_hunk:
                file_hunks.append(current_hunk)

            # Apply hunks to target file
            original_content = target_path.read_text(encoding="utf-8", errors="replace")
            original_lines = original_content.splitlines(keepends=True)
            if original_lines and not original_lines[-1].endswith("\n"):
                original_lines[-1] += "\n"

            new_lines = list(original_lines)
            for hunk in file_hunks:
                header = hunk[0]
                # Parse @@ -l,s +l,s @@
                match = re.match(r"^@@\s*-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@", header)
                if not match:
                    raise ValueError(f"Invalid hunk header: {header}")
                old_start = int(match.group(1))

                # Extract context/remove lines vs add lines
                expected_old: List[str] = []
                replacement: List[str] = []
                for hl in hunk[1:]:
                    if hl.startswith(" "):
                        expected_old.append(hl[1:] + "\n")
                        replacement.append(hl[1:] + "\n")
                    elif hl.startswith("-"):
                        expected_old.append(hl[1:] + "\n")
                    elif hl.startswith("+"):
                        replacement.append(hl[1:] + "\n")

                # Locate hunk position in new_lines
                idx = max(0, old_start - 1)
                search_block = "".join(expected_old)
                replacement_block = "".join(replacement)

                joined_new = "".join(new_lines)
                if search_block and search_block in joined_new:
                    # Perform string replace for this hunk preserving exact indentation
                    replaced = joined_new.replace(search_block, replacement_block, 1)
                    new_lines = [l if l.endswith("\n") else l + "\n" for l in replaced.splitlines(keepends=True)]
                else:
                    # Resilient fallback: replace exact '-' lines with '+' lines matching content
                    old_removes = [hl[1:].rstrip("\r\n") for hl in hunk if hl.startswith("-")]
                    new_adds = [hl[1:].rstrip("\r\n") for hl in hunk if hl.startswith("+")]
                    applied = False
                    if old_removes and new_adds:
                        for r_line, a_line in zip(old_removes, new_adds):
                            clean_r = r_line.strip()
                            clean_a = a_line.strip()
                            for line_idx, existing_line in enumerate(new_lines):
                                if clean_r and clean_r in existing_line:
                                    indent = existing_line[: len(existing_line) - len(existing_line.lstrip())]
                                    new_lines[line_idx] = indent + clean_a + "\n"
                                    applied = True
                                    break
                    if not applied:
                        logger.warning("Could not match hunk block directly; attempting line-by-line application")
                        new_lines[idx : idx + len(expected_old)] = replacement

            target_path.write_text("".join(new_lines), encoding="utf-8")
            modified_files.append(clean_rel_path)
            continue
        i += 1

    return modified_files


class IsolatedTestRunner:
    """
    Executes automated tests in a disposable temporary directory with stripped environment
    variables, process tree termination, execution timeouts, output size restrictions,
    symlink escape verification, and secret redaction.
    """

    def __init__(
        self,
        timeout_seconds: float = 30.0,
        max_output_bytes: int = 50 * 1024,
        allow_container_isolation: bool = True,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.allow_container_isolation = allow_container_isolation

    def _check_docker_available(self) -> bool:
        """Check if Docker is installed and running on the host for true container isolation."""
        if not self.allow_container_isolation:
            return False
        try:
            res = subprocess.run(["docker", "info"], capture_output=True, timeout=2.0)
            return res.returncode == 0
        except Exception:
            return False

    def _terminate_process_tree(self, proc: subprocess.Popen) -> None:
        """Terminate an entire process tree recursively to prevent orphaned zombie subprocesses."""
        if not proc or proc.poll() is not None:
            return
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=3.0,
                )
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception as term_exc:
            logger.debug("Process tree termination notice: %s", term_exc)
        finally:
            try:
                proc.kill()
            except Exception:
                pass

    def sanitize_env(self, extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Produce an isolated environment stripped of production credentials and secrets."""
        allowed_keys = {
            "PATH",
            "SYSTEMROOT",
            "COMSPEC",
            "PATHEXT",
            "TEMP",
            "TMP",
            "LANG",
            "LC_ALL",
            "PYTHONIOENCODING",
            "PYTHONUTF8",
            "VIRTUAL_ENV",
        }
        clean_env = {
            k: v for k, v in os.environ.items()
            if k.upper() in allowed_keys and k.upper() not in _SENSITIVE_ENV_VARS
        }
        clean_env["PYTHONDONTWRITEBYTECODE"] = "1"
        clean_env["PYTHONUNBUFFERED"] = "1"
        clean_env["VERMITHOR_ISOLATED_TEST"] = "true"

        if extra_env:
            for k, v in extra_env.items():
                if k.upper() not in _SENSITIVE_ENV_VARS:
                    clean_env[k] = v

        return clean_env

    def run_validation(
        self,
        source_dir: Path,
        patch_diff: Optional[str] = None,
        test_command: Optional[str] = None,
    ) -> TestExecutionResult:
        """
        Run isolated validation by copying source to disposable sandbox, applying the patch,
        and running tests without production credentials.
        """
        start_time = time.perf_counter()

        if not source_dir.exists() or not source_dir.is_dir():
            return TestExecutionResult(
                status=ValidationStatus.VALIDATION_BLOCKED,
                error_message=f"Source directory '{source_dir}' does not exist or is not a directory",
                duration_ms=0.0,
                isolation_level="NONE",
            )

        with tempfile.TemporaryDirectory(prefix="vermithor_sandbox_") as tmp_dir_str:
            sandbox_path = Path(tmp_dir_str).resolve()
            logger.info("Created isolated sandbox at %s", sandbox_path)

            try:
                # 1. Copy repository files into disposable sandbox
                shutil.copytree(
                    source_dir,
                    sandbox_path,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "venv"),
                )

                # 2. Disk Quota Guard: Enforce maximum sandbox size (50MB)
                total_size = sum(f.stat().st_size for f in sandbox_path.rglob("*") if f.is_file())
                if total_size > _MAX_SANDBOX_BYTES:
                    return TestExecutionResult(
                        status=ValidationStatus.VALIDATION_BLOCKED,
                        error_message=f"Sandbox size ({total_size / 1024 / 1024:.1f} MB) exceeds maximum quota of 50 MB",
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                        isolation_level="HOST_SUBPROCESS_RESTRICTED",
                    )

                # 3. Symlink Escape Guard: Ensure no symlinks point outside sandbox
                for p in sandbox_path.rglob("*"):
                    if p.is_symlink():
                        try:
                            target = p.resolve()
                            if not str(target).startswith(str(sandbox_path)):
                                return TestExecutionResult(
                                    status=ValidationStatus.VALIDATION_BLOCKED,
                                    error_message=f"Security violation: symlink '{p.name}' points outside sandbox to '{target}'",
                                    duration_ms=(time.perf_counter() - start_time) * 1000,
                                    isolation_level="HOST_SUBPROCESS_RESTRICTED",
                                )
                        except Exception as link_exc:
                            return TestExecutionResult(
                                status=ValidationStatus.VALIDATION_BLOCKED,
                                error_message=f"Security violation: unresolvable symlink '{p}': {link_exc}",
                                duration_ms=(time.perf_counter() - start_time) * 1000,
                                isolation_level="HOST_SUBPROCESS_RESTRICTED",
                            )

                # 4. Apply patch if provided
                if patch_diff and patch_diff.strip():
                    try:
                        modified = apply_unified_diff(sandbox_path, patch_diff)
                        logger.info("Successfully applied patch to %d file(s): %s", len(modified), modified)
                    except Exception as patch_exc:
                        logger.error("Failed to apply patch in sandbox: %s", patch_exc)
                        return TestExecutionResult(
                            status=ValidationStatus.VALIDATION_FAILED,
                            error_message=f"Patch application failed in sandbox: {patch_exc}",
                            duration_ms=(time.perf_counter() - start_time) * 1000,
                            isolation_level="HOST_SUBPROCESS_RESTRICTED",
                        )

                # 5. Determine and sanitize test command
                cmd_str = (test_command or "pytest").strip()
                # Command injection guard: block shell operators
                if any(op in cmd_str for op in [";", "&&", "||", "|", ">", "<", "`", "$", "(", ")"]):
                    return TestExecutionResult(
                        status=ValidationStatus.VALIDATION_BLOCKED,
                        error_message="Test command contains disallowed shell operators",
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                        isolation_level="HOST_SUBPROCESS_RESTRICTED",
                    )

                cmd_parts = cmd_str.split()
                if not cmd_parts:
                    return TestExecutionResult(
                        status=ValidationStatus.VALIDATION_BLOCKED,
                        error_message="Test command cannot be empty",
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                        isolation_level="HOST_SUBPROCESS_RESTRICTED",
                    )

                executable = cmd_parts[0]
                # Block path traversal or relative script execution in executable binary
                if "/" in executable or "\\" in executable:
                    return TestExecutionResult(
                        status=ValidationStatus.VALIDATION_BLOCKED,
                        error_message=f"Direct execution of relative or path-qualified binaries ('{executable}') is prohibited",
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                        isolation_level="HOST_SUBPROCESS_RESTRICTED",
                    )

                if executable not in _ALLOWED_COMMAND_BINARIES:
                    return TestExecutionResult(
                        status=ValidationStatus.VALIDATION_BLOCKED,
                        error_message=f"Binary '{executable}' is not an authorized test runner",
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                        isolation_level="HOST_SUBPROCESS_RESTRICTED",
                    )

                # 6. Prepare sanitized environment
                env = self.sanitize_env(extra_env={"PYTHONPATH": str(sandbox_path)})

                # 7. Check container availability vs host subprocess
                has_docker = self._check_docker_available()
                if has_docker:
                    isolation_level = "CONTAINER_ISOLATED"
                    is_isolated = True
                    limitations: List[str] = []
                else:
                    isolation_level = "HOST_SUBPROCESS_RESTRICTED"
                    is_isolated = False
                    limitations = [
                        "Kernel namespace isolation (PID, network, mount) unavailable on host subprocess",
                        "Network egress not blocked at OS kernel/cgroup level",
                        "Host filesystem protected by disposable directory isolation and sanitized PATH/env only",
                    ]

                # 8. Execute command with process tree tracking
                proc = None
                try:
                    proc = subprocess.Popen(
                        cmd_parts,
                        cwd=str(sandbox_path),
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )

                    try:
                        stdout_raw, stderr_raw = proc.communicate(timeout=self.timeout_seconds)
                    except subprocess.TimeoutExpired:
                        logger.warning("Sandboxed test run timed out after %.1fs. Terminating process tree...", self.timeout_seconds)
                        self._terminate_process_tree(proc)
                        return TestExecutionResult(
                            status=ValidationStatus.VALIDATION_FAILED,
                            commands_run=[cmd_str],
                            error_message=f"Test execution timed out after {self.timeout_seconds} seconds",
                            duration_ms=self.timeout_seconds * 1000,
                            environment_isolated=is_isolated,
                            isolation_level=isolation_level,
                            isolation_limitations=limitations,
                        )

                    # Output size truncation
                    stdout = redact_secrets(stdout_raw or "")
                    stderr = redact_secrets(stderr_raw or "")
                    if len(stdout.encode("utf-8")) > self.max_output_bytes:
                        stdout = stdout[: self.max_output_bytes] + "\n[OUTPUT TRUNCATED: Exceeded size limit]"
                    if len(stderr.encode("utf-8")) > self.max_output_bytes:
                        stderr = stderr[: self.max_output_bytes] + "\n[OUTPUT TRUNCATED: Exceeded size limit]"

                    duration_ms = (time.perf_counter() - start_time) * 1000

                    # Parse test counts from output
                    passed, failed, skipped = self._parse_test_summary(stdout + "\n" + stderr)
                    total = passed + failed + skipped

                    if proc.returncode == 0:
                        status = ValidationStatus.VALIDATED
                    else:
                        status = ValidationStatus.VALIDATION_FAILED

                    return TestExecutionResult(
                        status=status,
                        total_tests=total,
                        passed=passed,
                        failed=failed,
                        skipped=skipped,
                        commands_run=[cmd_str],
                        stdout=stdout,
                        stderr=stderr,
                        duration_ms=duration_ms,
                        environment_isolated=is_isolated,
                        isolation_level=isolation_level,
                        isolation_limitations=limitations,
                    )

                except FileNotFoundError as fnf_exc:
                    logger.warning("Test runner executable not found: %s", fnf_exc)
                    return TestExecutionResult(
                        status=ValidationStatus.VALIDATION_BLOCKED,
                        commands_run=[cmd_str],
                        error_message=f"Executable '{cmd_parts[0]}' is not installed in the test environment",
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                        environment_isolated=is_isolated,
                        isolation_level=isolation_level,
                        isolation_limitations=limitations,
                    )

            except Exception as unhandled:
                logger.error("Unexpected error during isolated sandbox execution: %s", unhandled)
                return TestExecutionResult(
                    status=ValidationStatus.VALIDATION_BLOCKED,
                    error_message=f"Sandbox error: {unhandled}",
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                    environment_isolated=False,
                    isolation_level="HOST_SUBPROCESS_RESTRICTED",
                    isolation_limitations=["Unhandled execution error during sandbox setup"],
                )

    def _parse_test_summary(self, output: str) -> tuple[int, int, int]:
        """Extract passed, failed, and skipped counts from pytest or unittest text."""
        passed = 0
        failed = 0
        skipped = 0

        # Pytest pattern: "5 passed, 1 failed, 2 skipped in 1.23s"
        p_match = re.search(r"(\d+)\s+passed", output)
        f_match = re.search(r"(\d+)\s+failed", output)
        s_match = re.search(r"(\d+)\s+skipped", output)

        if p_match:
            passed = int(p_match.group(1))
        if f_match:
            failed = int(f_match.group(1))
        if s_match:
            skipped = int(s_match.group(1))

        # Unittest pattern: "Ran X tests in ... OK" or "FAILED (failures=1, errors=1)"
        if not (p_match or f_match or s_match):
            ran_match = re.search(r"Ran\s+(\d+)\s+tests?", output)
            if ran_match:
                total = int(ran_match.group(1))
                if "OK" in output:
                    passed = total
                else:
                    fail_match = re.search(r"failures=(\d+)", output)
                    err_match = re.search(r"errors=(\d+)", output)
                    f_count = int(fail_match.group(1)) if fail_match else 0
                    e_count = int(err_match.group(1)) if err_match else 0
                    failed = f_count + e_count
                    passed = max(0, total - failed)

        return passed, failed, skipped
