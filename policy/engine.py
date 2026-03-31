"""
Helix Policy Engine — Governance & Compliance Framework
=========================================================

A lightweight policy-as-code engine inspired by OPA (Open Policy Agent) for:
- Agent boundary enforcement
- Resource access control
- Rate limiting and quota management
- Compliance and audit logging

Features:
- JSON-based policy definitions
- Context-aware rule evaluation
- Built-in policy templates
- Hot-reloadable policies
- Comprehensive audit trail

(c) Helix Collective 2025 - Proprietary Technology Stack
"""

import json
import logging
import os
import re
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# POLICY TYPES
# ============================================================================


class PolicyEffect(StrEnum):
    """Effect of a policy rule evaluation."""

    ALLOW = "allow"
    DENY = "deny"
    WARN = "warn"
    AUDIT = "audit"


class PolicyScope(StrEnum):
    """Scope of policy application."""

    AGENT = "agent"
    RESOURCE = "resource"
    API = "api"
    DATA = "data"
    SYSTEM = "system"


@dataclass
class PolicyCondition:
    """A condition that must be met for a policy rule to apply."""

    field: str  # JSONPath-like field path
    operator: str  # eq, neq, in, not_in, regex, gt, lt, gte, lte, exists, not_exists
    value: Any

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Evaluate this condition against a context."""
        # Extract field value from context
        field_value = self._get_field_value(context, self.field)

        # Resolve template variables in value (e.g., "${user.tenant_id}")
        resolved_value = self._resolve_value(context, self.value)

        # Apply operator
        if self.operator == "eq":
            return field_value == resolved_value
        elif self.operator == "neq":
            return field_value != resolved_value
        elif self.operator == "in":
            return field_value in resolved_value
        elif self.operator == "not_in":
            return field_value not in resolved_value
        elif self.operator == "regex":
            return bool(re.match(resolved_value, str(field_value)))
        elif self.operator == "gt":
            return field_value > resolved_value
        elif self.operator == "lt":
            return field_value < resolved_value
        elif self.operator == "gte":
            return field_value >= resolved_value
        elif self.operator == "lte":
            return field_value <= resolved_value
        elif self.operator == "exists":
            return field_value is not None
        elif self.operator == "not_exists":
            return field_value is None
        elif self.operator == "contains":
            return resolved_value in field_value if field_value else False
        elif self.operator == "not_contains":
            return resolved_value not in field_value if field_value else True
        else:
            logger.warning("Unknown operator: %s", self.operator)
            return False

    def _get_field_value(self, context: dict[str, Any], path: str) -> Any:
        """Get a field value from nested context using dot notation."""
        parts = path.split(".")
        value = context
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value

    def _resolve_value(self, context: dict[str, Any], value: Any) -> Any:
        """Resolve template variables like ${user.tenant_id} from context."""
        if not isinstance(value, str) or "${" not in value:
            return value
        match = re.fullmatch(r"\$\{([^}]+)\}", value)
        if match:
            return self._get_field_value(context, match.group(1))
        return value


@dataclass
class PolicyRule:
    """A single policy rule with conditions and effect."""

    name: str
    effect: PolicyEffect
    scope: PolicyScope
    conditions: list[PolicyCondition] = field(default_factory=list)
    priority: int = 100  # Lower = higher priority
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Check if all conditions match the context."""
        return all(cond.evaluate(context) for cond in self.conditions)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "effect": self.effect.value,
            "scope": self.scope.value,
            "conditions": [{"field": c.field, "operator": c.operator, "value": c.value} for c in self.conditions],
            "priority": self.priority,
            "message": self.message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyRule":
        """Create a PolicyRule from a dictionary."""
        conditions = [
            PolicyCondition(field=c["field"], operator=c["operator"], value=c["value"])
            for c in data.get("conditions", [])
        ]
        return cls(
            name=data["name"],
            effect=PolicyEffect(data["effect"]),
            scope=PolicyScope(data["scope"]),
            conditions=conditions,
            priority=data.get("priority", 100),
            message=data.get("message", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Policy:
    """A collection of policy rules with metadata."""

    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    rules: list[PolicyRule] = field(default_factory=list)
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "enabled": self.enabled,
            "rules": [r.to_dict() for r in self.rules],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Policy":
        """Create a Policy from a dictionary."""
        rules = [PolicyRule.from_dict(r) for r in data.get("rules", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            enabled=data.get("enabled", True),
            rules=rules,
        )


@dataclass
class PolicyDecision:
    """Result of a policy evaluation."""

    allowed: bool
    effect: PolicyEffect
    matched_rules: list[str]
    denied_by: list[str]
    warnings: list[str]
    audit_events: list[str]
    context: dict[str, Any]
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "allowed": self.allowed,
            "effect": self.effect.value,
            "matched_rules": self.matched_rules,
            "denied_by": self.denied_by,
            "warnings": self.warnings,
            "audit_events": self.audit_events,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


# ============================================================================
# POLICY STORE
# ============================================================================


class PolicyStore:
    """Storage and management for policies."""

    def __init__(self, policy_dir: str | None = None):
        self._policies: dict[str, Policy] = {}
        self._policy_dir = Path(policy_dir) if policy_dir else None
        self._custom_functions: dict[str, Callable] = {}

        # Load policies from directory if provided
        if self._policy_dir and self._policy_dir.exists():
            self.load_policies_from_dir(self._policy_dir)

    def register_function(self, name: str, func: Callable) -> None:
        """Register a custom function for policy evaluation."""
        self._custom_functions[name] = func
        logger.debug("Registered policy function: %s", name)

    def add_policy(self, policy: Policy) -> None:
        """Add or update a policy."""
        policy.updated_at = datetime.now(UTC)
        self._policies[policy.id] = policy
        logger.info("Added policy: %s (v%s)", policy.name, policy.version)

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy by ID."""
        if policy_id in self._policies:
            del self._policies[policy_id]
            logger.info("Removed policy: %s", policy_id)
            return True
        return False

    def get_policy(self, policy_id: str) -> Policy | None:
        """Get a policy by ID."""
        return self._policies.get(policy_id)

    def list_policies(self, scope: PolicyScope | None = None) -> list[Policy]:
        """List all policies, optionally filtered by scope."""
        policies = list(self._policies.values())
        if scope:
            policies = [p for p in policies if any(r.scope == scope for r in p.rules)]
        return policies

    def load_policies_from_dir(self, directory: Path) -> int:
        """Load policies from a directory of JSON files."""
        loaded = 0
        for policy_file in directory.glob("*.policy.json"):
            try:
                with open(policy_file) as f:
                    data = json.load(f)
                policy = Policy.from_dict(data)
                self.add_policy(policy)
                loaded += 1
            except Exception as e:
                logger.error("Failed to load policy from %s: %s", policy_file, e)
        return loaded

    def save_policy_to_file(self, policy: Policy, directory: Path | None = None) -> bool:
        """Save a policy to a JSON file."""
        save_dir = directory or self._policy_dir
        if not save_dir:
            logger.warning("No policy directory configured for saving")
            return False

        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        policy_file = save_dir / f"{policy.id}.policy.json"
        try:
            with open(policy_file, "w") as f:
                json.dump(policy.to_dict(), f, indent=2)
            logger.info("Saved policy to %s", policy_file)
            return True
        except Exception as e:
            logger.error("Failed to save policy to %s: %s", policy_file, e)
            return False


# ============================================================================
# POLICY ENGINE
# ============================================================================


class PolicyEngine:
    """
    Core policy evaluation engine.

    Evaluates policies against context to make allow/deny decisions.
    Supports:
    - Multiple policy scopes
    - Priority-based rule ordering
    - Custom functions for complex evaluations
    - Audit logging for compliance
    """

    def __init__(self, store: PolicyStore | None = None):
        self.store = store or PolicyStore()
        self._audit_log: deque = deque(maxlen=10000)

    @property
    def audit_log_count(self) -> int:
        """Return the number of entries in the audit log."""
        return len(self._audit_log)

    def evaluate(
        self,
        context: dict[str, Any],
        scope: PolicyScope | None = None,
        policies: list[str] | None = None,
    ) -> PolicyDecision:
        """
        Evaluate all applicable policies against the context.

        Args:
            context: The evaluation context (user, resource, action, etc.)
            scope: Optional scope filter
            policies: Optional list of specific policy IDs to evaluate

        Returns:
            PolicyDecision with allow/deny and matched rules
        """
        matched_rules: list[str] = []
        denied_by: list[str] = []
        warnings: list[str] = []
        audit_events: list[str] = []
        final_effect = PolicyEffect.ALLOW

        # Get applicable policies
        applicable_policies = self._get_applicable_policies(scope, policies)

        # Collect all rules and sort by priority
        all_rules: list[PolicyRule] = []
        for policy in applicable_policies:
            all_rules.extend(policy.rules)
        all_rules.sort(key=lambda r: r.priority)

        # Evaluate each rule
        for rule in all_rules:
            try:
                if rule.evaluate(context):
                    rule_id = rule.name
                    matched_rules.append(rule_id)

                    if rule.effect == PolicyEffect.DENY:
                        denied_by.append(rule_id)
                        final_effect = PolicyEffect.DENY
                    elif rule.effect == PolicyEffect.WARN:
                        warnings.append(rule.message or f"Warning from rule: {rule_id}")
                    elif rule.effect == PolicyEffect.AUDIT:
                        audit_events.append(rule.message or f"Audit: {rule_id}")
                        self._log_audit(rule, context)

                    logger.debug("Rule %s matched with effect %s", rule_id, rule.effect.value)
            except Exception as e:
                logger.error("Error evaluating rule %s: %s", rule.name, e)

        # Determine final decision
        allowed = final_effect != PolicyEffect.DENY

        decision = PolicyDecision(
            allowed=allowed,
            effect=final_effect,
            matched_rules=matched_rules,
            denied_by=denied_by,
            warnings=warnings,
            audit_events=audit_events,
            context=context,
        )

        # Log decision for audit
        self._log_decision(decision)

        return decision

    def evaluate_agent_access(
        self,
        agent_id: str,
        action: str,
        resource: str,
        user_id: str | None = None,
        session_id: str | None = None,
        additional_context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """
        Convenience method for agent access evaluation.

        Args:
            agent_id: The agent requesting access
            action: The action being performed (read, write, execute, etc.)
            resource: The resource being accessed
            user_id: Optional user ID
            session_id: Optional session ID
            additional_context: Additional context for evaluation

        Returns:
            PolicyDecision
        """
        context = {
            "agent": {
                "id": agent_id,
            },
            "action": action,
            "resource": resource,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if user_id:
            context["user"] = {"id": user_id}
        if session_id:
            context["session"] = {"id": session_id}
        if additional_context:
            context.update(additional_context)

        return self.evaluate(context, scope=PolicyScope.AGENT)

    def _get_applicable_policies(
        self,
        scope: PolicyScope | None = None,
        policy_ids: list[str] | None = None,
    ) -> list[Policy]:
        """Get policies applicable for evaluation."""
        policies = []

        if policy_ids:
            for pid in policy_ids:
                policy = self.store.get_policy(pid)
                if policy and policy.enabled:
                    policies.append(policy)
        else:
            policies = [p for p in self.store.list_policies() if p.enabled]

        if scope:
            policies = [p for p in policies if any(r.scope == scope for r in p.rules)]

        return policies

    def _log_audit(self, rule: PolicyRule, context: dict[str, Any]) -> None:
        """Log an audit event."""
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "rule": rule.name,
            "scope": rule.scope.value,
            "context": context,
            "message": rule.message,
        }
        self._audit_log.append(event)

    def _log_decision(self, decision: PolicyDecision) -> None:
        """Log a policy decision."""
        event = {
            "timestamp": decision.evaluated_at.isoformat(),
            "type": "decision",
            "allowed": decision.allowed,
            "effect": decision.effect.value,
            "matched_rules": decision.matched_rules,
            "denied_by": decision.denied_by,
            "context": decision.context,
        }
        self._audit_log.append(event)

    def get_audit_log(
        self,
        limit: int = 100,
        rule_name: str | None = None,
        allowed_only: bool | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get audit log entries with optional filtering.

        Args:
            limit: Maximum number of entries to return
            rule_name: Filter by rule name
            allowed_only: Filter by allowed/denied
        """
        entries = list(reversed(self._audit_log))

        if rule_name:
            entries = [e for e in entries if e.get("rule") == rule_name]
        if allowed_only is not None:
            entries = [e for e in entries if e.get("allowed") == allowed_only]

        return entries[:limit]

    def clear_audit_log(self) -> int:
        """Clear the audit log and return count of removed entries."""
        count = len(self._audit_log)
        self._audit_log.clear()
        return count


# ============================================================================
# BUILT-IN POLICIES
# ============================================================================


def create_default_policies() -> list[Policy]:
    """Create default policies for Helix platform."""
    policies = []

    # Agent Rate Limiting Policy
    rate_limit_policy = Policy(
        id="agent-rate-limits",
        name="Agent Rate Limits",
        description="Enforce rate limits on agent actions",
        rules=[
            PolicyRule(
                name="deny-excessive-calls",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="agent.calls_per_minute", operator="gt", value=100),
                ],
                priority=10,
                message="Rate limit exceeded: agent has made over 100 calls per minute",
            ),
            PolicyRule(
                name="warn-high-activity",
                effect=PolicyEffect.WARN,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="agent.calls_per_minute", operator="gt", value=50),
                ],
                priority=20,
                message="High activity detected: over 50 calls per minute",
            ),
        ],
    )
    policies.append(rate_limit_policy)

    # Agent Boundary Policy
    boundary_policy = Policy(
        id="agent-boundaries",
        name="Agent Boundaries",
        description="Enforce agent capability boundaries",
        rules=[
            PolicyRule(
                name="deny-cross-tenant-access",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="agent.tenant_id", operator="exists", value=None),
                    PolicyCondition(field="user.tenant_id", operator="exists", value=None),
                    PolicyCondition(field="agent.tenant_id", operator="neq", value="${user.tenant_id}"),
                ],
                priority=5,
                message="Cross-tenant access denied",
            ),
            PolicyRule(
                name="audit-sensitive-actions",
                effect=PolicyEffect.AUDIT,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="action", operator="in", value=["delete", "admin", "export"]),
                ],
                priority=50,
                message="Sensitive action performed",
            ),
        ],
    )
    policies.append(boundary_policy)

    # Resource Access Policy
    resource_policy = Policy(
        id="resource-access",
        name="Resource Access Control",
        description="Control access to sensitive resources",
        rules=[
            PolicyRule(
                name="deny-system-resource-access",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.RESOURCE,
                conditions=[
                    PolicyCondition(field="resource", operator="regex", value=r"^system\..*"),
                    PolicyCondition(field="user.role", operator="neq", value="admin"),
                ],
                priority=5,
                message="Only admins can access system resources",
            ),
            PolicyRule(
                name="audit-financial-data-access",
                effect=PolicyEffect.AUDIT,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="resource", operator="regex", value=r"^financial\..*"),
                ],
                priority=50,
                message="Financial data accessed",
            ),
        ],
    )
    policies.append(resource_policy)

    # API Security Policy
    api_policy = Policy(
        id="api-security",
        name="API Security",
        description="API access control and security policies",
        rules=[
            PolicyRule(
                name="deny-unauthenticated-admin",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.API,
                conditions=[
                    PolicyCondition(field="api.endpoint", operator="regex", value=r"^/admin/.*"),
                    PolicyCondition(field="user.authenticated", operator="eq", value=False),
                ],
                priority=1,
                message="Authentication required for admin endpoints",
            ),
            PolicyRule(
                name="rate-limit-api-calls",
                effect=PolicyEffect.WARN,
                scope=PolicyScope.API,
                conditions=[
                    PolicyCondition(field="api.calls_per_minute", operator="gt", value=60),
                ],
                priority=30,
                message="High API call rate detected",
            ),
        ],
    )
    policies.append(api_policy)

    return policies


# ============================================================================
# SINGLETON & HELPER
# ============================================================================


_engine: PolicyEngine | None = None
_store: PolicyStore | None = None


def get_policy_store() -> PolicyStore:
    """Get the global policy store instance."""
    global _store
    if _store is None:
        policy_dir = os.getenv("HELIX_POLICY_DIR", "policies")
        _store = PolicyStore(policy_dir=policy_dir)

        # Load default policies
        for policy in create_default_policies():
            _store.add_policy(policy)

    return _store


def get_policy_engine() -> PolicyEngine:
    """Get the global policy engine instance."""
    global _engine
    if _engine is None:
        _engine = PolicyEngine(store=get_policy_store())
    return _engine


def check_policy(
    context: dict[str, Any],
    scope: PolicyScope | None = None,
) -> PolicyDecision:
    """
    Quick helper to check policy for a context.

    Usage:
        decision = check_policy({"user": {"id": "123"}, "action": "read"})
        if not decision.allowed:
            raise PermissionError(decision.denied_by[0])
    """
    return get_policy_engine().evaluate(context, scope=scope)
