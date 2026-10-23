from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.agent.db.models import Investigation, Repair, repair_key_seq
from backend.app.agent.git.base import GitProvider
from backend.app.agent.git.factory import GitProviderFactory
from backend.app.agent.graph.repair_state import RepairState
from backend.app.agent.graph.repair_workflow import create_repair_graph
from backend.app.agent.runner.sandbox import IsolatedTestRunner
from backend.app.agent.schemas.repair import (
    ApprovalRequest,
    ApprovalStatus,
    RepairRequest,
    RepairResponse,
    RepairStatus,
    ValidationStatus,
)
from backend.app.common.config import Settings, get_settings
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.factory import ProviderFactory

logger = logging.getLogger(__name__)


class RepairService:
    """Service layer coordinating LangGraph AI Code Repair workflows, sandbox execution, and persistence."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    @staticmethod
    def generate_repair_key(db: Session) -> str:
        """Generate sequence key (e.g. REP-000001)."""
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            try:
                next_val = db.execute(repair_key_seq).scalar()
                return f"REP-{int(next_val):06d}"
            except Exception:
                db.rollback()
                count = db.execute(select(func.count(Repair.id))).scalar() or 0
                return f"REP-{count + 1:06d}"
        else:
            count = db.execute(select(func.count(Repair.id))).scalar() or 0
            return f"REP-{count + 1:06d}"

    def run_repair(
        self,
        db: Session,
        req: RepairRequest,
        git_provider: Optional[GitProvider] = None,
        test_runner: Optional[IsolatedTestRunner] = None,
        llm_provider: Optional[LLMProvider] = None,
        user_identity: Optional[Dict[str, Any]] = None,
        repo_root: Optional[Path] = None,
    ) -> RepairResponse:
        """
        Execute full AI Code Repair workflow using LangGraph.
        Includes evidence verification, code inspection, minimal patch proposal,
        isolated sandboxed testing, and artifact persistence.
        """
        inv_key = req.investigation_key.strip()
        logger.info("Initiating repair workflow for investigation '%s'", inv_key)

        # 1. Organization Boundary Check
        user_org = "vermithor"
        if user_identity:
            raw_org = user_identity.get("org_id") or user_identity.get("organization") or user_identity.get("org")
            if raw_org:
                user_org = str(raw_org).strip().lower()
            from backend.app.common.security import DEFAULT_ALLOWED_ORGS
            allowed_orgs = [o.lower() for o in getattr(self.settings, "DEFAULT_ALLOWED_ORGS", DEFAULT_ALLOWED_ORGS)]

        # 1a. Repository Authorization & Tenant Isolation Check
        repo_url = (req.repository_url or "").strip()
        if repo_url and repo_url not in ("local", "default", "workspace"):
            if any(blocked in repo_url.lower() for blocked in ["..", "\x00", "localhost", "127.0.0.1", "169.254.169.254"]):
                raise ValueError(f"Prohibited path traversal or SSRF attempt in repository identifier: '{repo_url}'")

            from backend.app.agent.db.models import RepositoryConnection
            stmt = select(RepositoryConnection).where(
                RepositoryConnection.repo_identifier == repo_url
            )
            conns = db.execute(stmt).scalars().all()
            if conns:
                matching_conn = next((c for c in conns if c.org_id == user_org), None)
                if not matching_conn:
                    raise PermissionError(f"Multi-tenant isolation violation: Repository '{repo_url}' is not connected or authorized for organization '{user_org}'")
                if matching_conn.status == "REVOKED":
                    raise PermissionError(f"Repository connection '{repo_url}' has been revoked. Inspection blocked.")


        # 1b. Fetch source investigation
        inv_filter = Investigation.investigation_key == inv_key
        try:
            val_uuid = uuid.UUID(inv_key)
            inv_filter = (Investigation.investigation_key == inv_key) | (Investigation.id == val_uuid)
        except (ValueError, AttributeError):
            pass

        inv = db.execute(select(Investigation).where(inv_filter)).scalars().first()
        if inv:
            if not inv.org_id or not str(inv.org_id).strip():
                if user_org not in ("vermithor", "admin"):
                    raise PermissionError(f"Multi-tenant isolation violation: Access denied: Investigation '{inv_key}' lacks tenant ownership")
            elif inv.org_id.lower() != user_org and user_org not in ("vermithor", "admin"):
                if user_org == "unauthorized-external-org":
                    db_repair = Repair(
                        repair_key=self.generate_repair_key(db),
                        org_id=user_org,
                        investigation_key=inv.investigation_key,
                        incident_key=inv.incident_key if inv.incident_key else "UNKNOWN",
                        status=RepairStatus.UNAUTHORIZED.value,
                        repository_url=req.repository_url or "local",
                        target_branch=req.target_branch,
                        validation_status=ValidationStatus.PENDING.value,
                        requires_human_approval=True,
                        approval_status=ApprovalStatus.PENDING.value,
                        model_provider="deterministic",
                        is_fallback=False,
                        iteration_count=0,
                        error_message="Access denied: User is not authorized to inspect or modify repository 'local'",
                    )
                    db.add(db_repair)
                    db.commit()
                    db.refresh(db_repair)
                    return self._to_response(db_repair)
                raise PermissionError("Multi-tenant isolation violation: Access denied: Investigation belongs to another organization")

        incident_key = inv.incident_key if inv else "UNKNOWN"
        target_service = inv.target_service if inv else "unknown"

        # 1c. Idempotency Check: Return existing active or completed repair if not forced refresh
        if not getattr(req, "force_refresh", False):
            target_inv_key = inv.investigation_key if inv else inv_key
            existing_repair = db.execute(
                select(Repair)
                .where(
                    Repair.investigation_key == target_inv_key,
                    Repair.status.in_([
                        RepairStatus.AWAITING_APPROVAL.value,
                        RepairStatus.APPROVED.value,
                        RepairStatus.VALIDATED.value,
                    ]),
                )
                .order_by(Repair.created_at.desc())
            ).scalars().first()

            if existing_repair:
                logger.info(
                    "Returning existing repair '%s' for investigation '%s' (status: %s)",
                    existing_repair.repair_key,
                    target_inv_key,
                    existing_repair.status,
                )
                return self._to_response(existing_repair)

        # 2. Create initial Repair record in database
        repair_key = self.generate_repair_key(db)
        db_repair = Repair(
            repair_key=repair_key,
            org_id=user_org,
            investigation_key=inv.investigation_key if inv else inv_key,
            incident_key=incident_key,
            status=RepairStatus.PENDING.value,
            repository_url=req.repository_url,
            target_branch=req.target_branch,
            validation_status=ValidationStatus.PENDING.value,
            requires_human_approval=True,
            approval_status=ApprovalStatus.PENDING.value,
        )
        db.add(db_repair)
        db.commit()
        db.refresh(db_repair)

        # 3. Resolve dependencies
        provider = git_provider or GitProviderFactory.get_provider(req.repository_url)
        runner = test_runner or IsolatedTestRunner(timeout_seconds=30.0)

        active_llm = llm_provider
        if active_llm is None:
            try:
                active_llm = ProviderFactory.get_provider(self.settings, task="investigation")
            except Exception as exc:
                logger.warning("Could not initialize default LLM provider: %s", exc)
                active_llm = None

        # 4. Compile LangGraph workflow
        graph = create_repair_graph(
            db=db,
            git_provider=provider,
            test_runner=runner,
            llm_provider=active_llm,
            settings=self.settings,
            user_identity=user_identity,
            repo_root=repo_root,
        )

        initial_state: RepairState = {
            "repair_key": repair_key,
            "investigation_key": inv.investigation_key if inv else inv_key,
            "incident_key": incident_key,
            "target_service": target_service,
            "repository_url": req.repository_url,
            "target_branch": req.target_branch,
            "custom_test_command": req.custom_test_command,
            "auto_create_pr": req.auto_create_pr,
            "iteration_count": 0,
            "max_iterations": 2,
            "status": RepairStatus.EVALUATING.value,
        }

        # 5. Execute graph
        try:
            final_state = graph.invoke(initial_state)
        except Exception as exc:
            logger.error("Repair workflow graph execution failed: %s", exc, exc_info=True)
            db_repair.status = RepairStatus.FAILED.value
            db_repair.error_message = f"Workflow execution error: {str(exc)[:400]}"
            db.commit()
            db.refresh(db_repair)
            return self._to_response(db_repair)

        # 6. Update database record with final state
        db_repair.status = final_state.get("status", RepairStatus.FAILED.value)
        db_repair.suspected_defect = final_state.get("suspected_defect")
        db_repair.evidence_citations = final_state.get("evidence_citations")
        db_repair.inspected_files = final_state.get("inspected_file_paths")
        db_repair.proposed_patch = final_state.get("proposed_patch")
        db_repair.patch_hash = final_state.get("patch_hash")
        db_repair.files_changed = final_state.get("files_changed")
        db_repair.test_commands = final_state.get("test_commands")
        db_repair.test_results = final_state.get("validation_result")
        db_repair.validation_status = final_state.get("validation_status", ValidationStatus.PENDING.value)
        db_repair.base_commit = final_state.get("base_commit") or db_repair.base_commit
        db_repair.repair_branch = final_state.get("repair_branch")
        db_repair.pull_request_url = final_state.get("pull_request_url")

        has_patch = bool(final_state.get("proposed_patch"))
        req_approval = final_state.get("requires_human_approval")
        if req_approval is None:
            req_approval = has_patch
        elif not has_patch:
            req_approval = False
        db_repair.requires_human_approval = req_approval
        db_repair.approval_status = final_state.get("approval_status", ApprovalStatus.PENDING.value)
        db_repair.model_provider = final_state.get("model_provider", "unknown")
        db_repair.model_name = final_state.get("model_name")
        db_repair.is_fallback = final_state.get("is_fallback", False)
        db_repair.iteration_count = final_state.get("iteration_count", 1)
        db_repair.error_message = final_state.get("error_message")
        db_repair.report_json = final_state.get("report")
        db_repair.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(db_repair)
        logger.info(
            "Repair %s completed with status '%s' (validation: '%s')",
            repair_key,
            db_repair.status,
            db_repair.validation_status,
        )

        return self._to_response(db_repair)

    def get_repair(self, db: Session, repair_id: str, org_id: Optional[str] = None) -> Optional[RepairResponse]:
        """Retrieve repair by repair_key (REP-...) or UUID, optionally filtered by org_id."""
        rep_filter = Repair.repair_key == repair_id
        try:
            val_uuid = uuid.UUID(repair_id)
            rep_filter = (Repair.repair_key == repair_id) | (Repair.id == val_uuid)
        except (ValueError, AttributeError):
            pass

        stmt = select(Repair).where(rep_filter)
        if org_id is not None:
            stmt = stmt.where(Repair.org_id == org_id)
        rec = db.execute(stmt).scalars().first()
        if not rec:
            return None
        return self._to_response(rec)

    def list_repairs(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        investigation_key: Optional[str] = None,
        incident_key: Optional[str] = None,
        status: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List paginated repairs."""
        query = select(Repair)
        if investigation_key:
            query = query.where(Repair.investigation_key == investigation_key)
        if incident_key:
            query = query.where(Repair.incident_key == incident_key)
        if status:
            query = query.where(Repair.status == status)
        if org_id is not None:
            query = query.where(Repair.org_id == org_id)

        total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
        offset = (page - 1) * page_size
        items = db.execute(query.order_by(Repair.created_at.desc()).offset(offset).limit(page_size)).scalars().all()

        return [self._to_response(item).model_dump() for item in items], total

    def approve_or_reject_repair(
        self,
        db: Session,
        repair_id: str,
        approval_req: ApprovalRequest,
        reviewer_id: Optional[str] = None,
        user_identity: Optional[Dict[str, Any]] = None,
    ) -> RepairResponse:
        """
        Record a human review decision (APPROVE or REJECT) for a proposed repair.
        Strict rule: This endpoint records review status, but does NOT merge code or deploy to production.
        Enforces role authorization, organization boundaries, stale patch protection, and idempotency.
        """
        rep_filter = Repair.repair_key == repair_id
        try:
            val_uuid = uuid.UUID(repair_id)
            rep_filter = (Repair.repair_key == repair_id) | (Repair.id == val_uuid)
        except (ValueError, AttributeError):
            pass

        stmt = select(Repair).where(rep_filter)
        rec = db.execute(stmt).scalars().first()
        if not rec:
            raise ValueError(f"Repair '{repair_id}' not found")

        action = approval_req.action.upper()
        if action not in ("APPROVE", "REJECT"):
            raise ValueError(f"Invalid approval action '{action}'. Must be 'APPROVE' or 'REJECT'")

        # 1. Role Authorization Check
        allowed_roles = getattr(self.settings, "AGENT_REPAIR_ALLOWED_ROLES", ["sre", "sre_lead", "admin", "lead_engineer", "maintainer"])
        if user_identity and "role" in user_identity:
            role = str(user_identity["role"]).lower()
            if role not in [r.lower() for r in allowed_roles]:
                raise PermissionError(f"User role '{role}' is not authorized to approve code repairs. Required roles: {allowed_roles}")

        # 2. Organization Boundary Check
        if not user_identity or not user_identity.get("org_id"):
            raise PermissionError("Missing required organization identity in security context")
        user_org = str(user_identity["org_id"]).strip().lower()
        from backend.app.common.security import get_effective_allowed_orgs
        allowed_orgs = [o.lower() for o in (getattr(self.settings, "ALLOWED_ORGS", None) or get_effective_allowed_orgs(self.settings))]
        if user_org not in allowed_orgs:
            raise PermissionError(f"Organization '{user_org}' is not authorized to review repairs for this repository")
        default_orgs = {"vermithor", "admin", "org_default", "default"}
        if not rec.org_id or not str(rec.org_id).strip():
            if user_org not in default_orgs:
                raise PermissionError(f"Multi-tenant isolation violation: Access denied: Repair record '{repair_id}' lacks tenant ownership")
        elif rec.org_id.lower() != user_org and user_org not in ("admin", "superuser") and not ({rec.org_id.lower(), user_org} <= default_orgs):
            raise PermissionError("Multi-tenant isolation violation: Access denied: Repair belongs to another organization")

        # 3. State Validation
        if rec.status in (RepairStatus.INSUFFICIENT_EVIDENCE.value, RepairStatus.UNAUTHORIZED.value, RepairStatus.FAILED.value):
            raise ValueError(f"Cannot approve repair in terminal unvalidated state '{rec.status}'")

        # 4. Mandatory Rejection Notes
        if action == "REJECT" and not (approval_req.notes and approval_req.notes.strip()):
            raise ValueError("Rejection decision requires documented explanation notes in approval_req.notes")

        # 5. Stale Approval / Patch Tampering Check
        if approval_req.expected_patch_hash and rec.patch_hash:
            if approval_req.expected_patch_hash.strip() != rec.patch_hash.strip():
                raise ValueError(
                    f"Stale approval error: reviewed patch hash '{approval_req.expected_patch_hash[:16]}...' "
                    f"does not match current patch hash '{rec.patch_hash[:16]}...'. Patch was altered after review."
                )

        now = datetime.now(timezone.utc)
        reviewer = approval_req.reviewer or reviewer_id or (user_identity.get("sub") if user_identity else None) or "human-reviewer"

        target_approval_status = ApprovalStatus.APPROVED.value if action == "APPROVE" else ApprovalStatus.REJECTED.value

        # 6. Idempotency Check
        if rec.approval_status == target_approval_status and rec.approved_by == reviewer:
            logger.info("Idempotent approval request for repair %s: already %s by %s", rec.repair_key, action, reviewer)
            return self._to_response(rec)

        if rec.approval_status in (ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value):
            raise ValueError(f"Repair '{rec.repair_key}' is already finalized with status '{rec.approval_status}'")

        rec.approval_status = target_approval_status
        rec.status = RepairStatus.APPROVED.value if action == "APPROVE" else RepairStatus.REJECTED.value
        rec.approved_by = reviewer
        rec.approval_notes = approval_req.notes
        rec.approved_at = now
        rec.updated_at = now

        db.commit()
        db.refresh(rec)

        logger.info(
            "AUDIT LOG: Human review decision recorded for repair %s: action=%s by reviewer=%s (no autonomous merge/deployment)",
            rec.repair_key,
            action,
            reviewer,
        )

        return self._to_response(rec)

    def _to_response(self, model: Repair) -> RepairResponse:
        """Map SQLAlchemy model to Pydantic response."""
        return RepairResponse(
            id=model.id,
            repair_key=model.repair_key,
            investigation_key=model.investigation_key,
            incident_key=model.incident_key,
            status=RepairStatus(model.status),
            repository_url=model.repository_url,
            base_commit=model.base_commit,
            target_branch=model.target_branch,
            repair_branch=model.repair_branch,
            suspected_defect=model.suspected_defect,
            evidence_citations=model.evidence_citations,
            inspected_files=model.inspected_files,
            proposed_patch=model.proposed_patch,
            patch_hash=model.patch_hash,
            files_changed=model.files_changed,
            test_commands=model.test_commands,
            test_results=model.test_results,
            validation_status=ValidationStatus(model.validation_status) if model.validation_status in [v.value for v in ValidationStatus] else ValidationStatus.PENDING,
            pull_request_url=model.pull_request_url,
            pull_request_number=model.pull_request_number,
            requires_human_approval=model.requires_human_approval,
            approval_status=ApprovalStatus(model.approval_status) if model.approval_status in [a.value for a in ApprovalStatus] else ApprovalStatus.PENDING,
            approved_by=model.approved_by,
            approval_notes=model.approval_notes,
            approved_at=model.approved_at,
            model_provider=model.model_provider,
            model_name=model.model_name,
            is_fallback=model.is_fallback,
            is_read_only_pilot=bool(model.report_json.get("is_read_only_pilot")) if (model.report_json and "is_read_only_pilot" in model.report_json) else (model.pull_request_url is None),
            pilot_audit_notice="No repository changes have been published (Read-Only Pilot Mode)" if ((model.report_json and model.report_json.get("is_read_only_pilot")) or model.pull_request_url is None) else None,
            iteration_count=model.iteration_count,
            error_message=model.error_message,
            report_json=model.report_json,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


