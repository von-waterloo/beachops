"""Deterministic safety classification for control-plane jobs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from beachops.domain.security import ApprovalKind, JobKind, RiskLevel

_RAW_SHELL_RE = re.compile(
    r"(?im)^\s*(?:sudo\s+|bash\s+-c\s+|sh\s+-c\s+|"
    r"rm\s+|chmod\s+|chown\s+|curl\s+|wget\s+|"
    r"docker\s+(?:exec|run)\s+|"
    r"docker\s+compose\s+(?:up|down|run|exec|build|restart|stop|rm|pull|push)\b|"
    r"kubectl\s+(?:apply|create|delete|edit|exec|patch|replace|rollout|scale)\b)"
)
_FORCE_RE = re.compile(
    r"(?i)\b(?:git\s+push\s+--force(?:-with-lease)?|force[- ]push|"
    r"delete\s+(?:the\s+)?(?:main|master)\s+branch)\b"
)
_SECRET_EXFIL_RE = re.compile(
    r"(?i)\b(?:show|print|dump|send|export|reveal|read|copy)\b"
    r".{0,40}\b(?:secret|password|token|api[_ -]?key|private[_ -]?key|\.env)\b"
)
_DESTRUCTIVE_RE = re.compile(
    r"(?i)\b(?:rm\s+-rf|drop\s+(?:database|schema)|truncate\s+table|"
    r"delete\s+from\s+\S+\s*(?:;|$)|delete\s+(?:all|everything))\b"
)
_DEPLOY_RE = re.compile(
    r"(?i)\b(?:deploy|release|roll\s*out|promote)\b.{0,40}"
    r"\b(?:prod|production|live)\b"
)
_MERGE_RE = re.compile(
    r"(?i)\b(?:merge|squash\s+and\s+merge|rebase\s+and\s+merge)\b"
    r".{0,40}\b(?:pr|pull\s+request|main|master|branch)\b"
)
_PROD_DB_RE = re.compile(
    r"(?i)\b(?:update|insert|delete|alter|drop|truncate|migrate)\b"
    r".{0,60}\b(?:prod(?:uction)?\s+(?:db|database)|production\s+postgres)\b"
)
_IAM_RE = re.compile(
    r"(?i)\b(?:grant|revoke|assign|remove|create)\b.{0,50}"
    r"\b(?:admin|owner|role|permission|iam|service\s+account|access)\b"
)
_DELETE_RE = re.compile(
    r"(?i)\b(?:delete|destroy|purge|remove)\b.{0,50}"
    r"\b(?:repository|repo|branch|database|table|account|environment|volume)\b"
)
_READ_ONLY_REQUEST_RE = re.compile(
    r"(?i)^\s*(?:please\s+)?(?:explain|describe|document|analy[sz]e|review|"
    r"summarize|what\b|why\b|how\b|where\b)"
)
# Safety / scope lines that forbid an action — strip before high-risk matching
# so "Do NOT merge to main" does not look like a merge request.
_NEGATED_RISK_CLAUSE_RE = re.compile(
    r"(?i)(?:"
    r"(?:do\s+not|don't|dont|never|no(?:\s+need\s+to)?)\s+"
    r"(?:merge|deploy|release|promote|delete|destroy|force[- ]?push|roll\s*out)"
    r"(?:\s+\w+){0,8}"
    r"|"
    r"(?:не\s+(?:надо\s+|нужно\s+)?(?:мерж\w*|депло\w*|рели\w*|удал\w*|пуш\w*)|"
    r"без\s+(?:merge|merging|deploy(?:ment)?|деплоя|релиза)|"
    r"(?:merge|deploy|release|деплой|мерж)\s+не\s+(?:делай|нужен|нужно))"
    r"(?:\s+\w+){0,8}"
    r")"
)


def _text_for_risk_match(text: str) -> str:
    return _NEGATED_RISK_CLAUSE_RE.sub(" ", text)


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    blocked: bool
    reasons: tuple[str, ...] = ()
    approval_kind: ApprovalKind | None = None

    @property
    def requires_approval(self) -> bool:
        return self.level == RiskLevel.HIGH and not self.blocked


class RiskPolicy:
    """Classify intended actions; prose mentions alone remain read-only."""

    def assess(
        self,
        text: str,
        *,
        job_kind: JobKind = JobKind.READ,
        branch: str | None = None,
        write: bool = False,
    ) -> RiskAssessment:
        normalized_branch = (branch or "").strip().lower()
        if write and normalized_branch in {"main", "master"}:
            return _blocked("write to protected branch")
        if job_kind == JobKind.RAW_SHELL:
            return _blocked("arbitrary shell execution")
        if job_kind == JobKind.SECRETS:
            return _blocked("secret access or exfiltration")
        if job_kind == JobKind.DEPLOY:
            return _high("production deployment", ApprovalKind.DEPLOY)
        if job_kind == JobKind.MERGE:
            return _high("repository merge", ApprovalKind.MERGE)
        if job_kind == JobKind.PROD_DB:
            return _high("production database write", ApprovalKind.PROD_DB)
        if job_kind == JobKind.IAM:
            return _high("identity or access change", ApprovalKind.IAM)
        if job_kind == JobKind.DELETE:
            return _high("destructive resource change", ApprovalKind.DESTRUCTIVE)
        if not write and _READ_ONLY_REQUEST_RE.match(text):
            return RiskAssessment(level=RiskLevel.LOW, blocked=False)

        match_text = _text_for_risk_match(text)

        if _RAW_SHELL_RE.search(match_text):
            return _blocked("arbitrary shell execution")
        if _FORCE_RE.search(match_text):
            return _blocked("force or protected-branch operation")
        if _SECRET_EXFIL_RE.search(match_text):
            return _blocked("secret access or exfiltration")
        if _DESTRUCTIVE_RE.search(match_text):
            return _blocked("destructive command")

        if _DEPLOY_RE.search(match_text):
            return _high("production deployment", ApprovalKind.DEPLOY)
        if _MERGE_RE.search(match_text):
            return _high("repository merge", ApprovalKind.MERGE)
        if _PROD_DB_RE.search(match_text):
            return _high("production database write", ApprovalKind.PROD_DB)
        if _IAM_RE.search(match_text):
            return _high("identity or access change", ApprovalKind.IAM)
        if _DELETE_RE.search(match_text):
            return _high("destructive resource change", ApprovalKind.DESTRUCTIVE)
        if job_kind == JobKind.CHANGE or write:
            return RiskAssessment(
                level=RiskLevel.MEDIUM,
                blocked=False,
                reasons=("repository write",),
            )
        return RiskAssessment(level=RiskLevel.LOW, blocked=False)


def assess_risk(
    text: str,
    *,
    job_kind: JobKind = JobKind.READ,
    branch: str | None = None,
    write: bool = False,
) -> RiskAssessment:
    return RiskPolicy().assess(
        text,
        job_kind=job_kind,
        branch=branch,
        write=write,
    )


def _blocked(reason: str) -> RiskAssessment:
    return RiskAssessment(
        level=RiskLevel.BLOCKED,
        blocked=True,
        reasons=(reason,),
    )


def _high(reason: str, approval_kind: ApprovalKind) -> RiskAssessment:
    return RiskAssessment(
        level=RiskLevel.HIGH,
        blocked=False,
        reasons=(reason,),
        approval_kind=approval_kind,
    )
