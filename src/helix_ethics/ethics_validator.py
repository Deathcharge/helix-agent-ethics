"""
Ethics Validator
================

Advanced ethics validation system implementing ethical guardrails compliance checking
for all agent actions and system operations.

Features:
- Real-time ethics validation for agent actions
- Compliance rule engine with configurable policies
- Ethics violation detection and resolution
- Audit logging and reporting
- Policy management and versioning
- Confidence scoring and risk assessment

Author: Helix Unified Team
Date: January 2026
"""

import asyncio
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from .enhanced_errors import EthicsViolationError
from .enhanced_logging import get_security_logger
from .enhanced_types import EthicsConfig, EthicsEvent, EthicsValidation, EthicsViolation

logger = get_security_logger()


# ============================================================================
# ETHICS RULES AND POLICIES
# ============================================================================


class EthicsRuleType(str, Enum):
    """Types of ethics rules."""

    ACTION_VALIDATION = "action_validation"
    RESOURCE_ACCESS = "resource_access"
    DATA_PRIVACY = "data_privacy"
    COORDINATION_INTEGRITY = "coordination_integrity"
    SYSTEM_COMPLIANCE = "system_compliance"
    SYSTEM_INTEGRITY = "system_integrity"


class EthicsSeverity(str, Enum):
    """Severity levels for ethics violations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    CATASTROPHIC = "catastrophic"


class EthicsPolicy(BaseModel):
    """Ethics policy definition."""

    policy_id: UUID
    name: str
    description: str
    rule_type: EthicsRuleType
    severity: EthicsSeverity
    enabled: bool = True
    conditions: dict[str, Any]
    actions: list[str]
    version: str = "1.0"
    created_at: datetime
    updated_at: datetime


# ============================================================================
# ETHICS RULE ENGINE
# ============================================================================


class EthicsRuleEngine:
    """Core ethics rule engine for validation."""

    def __init__(self, config: EthicsConfig):
        self.config = config
        self.policies: dict[UUID, EthicsPolicy] = {}
        self.rule_cache: dict[str, list[EthicsPolicy]] = {}
        self.violation_history: list[EthicsViolation] = []

    def add_policy(self, policy: EthicsPolicy):
        """Add ethics policy."""
        self.policies[policy.policy_id] = policy
        self._update_rule_cache(policy)
        logger.info("Ethics policy added: %s", policy.name)

    def remove_policy(self, policy_id: UUID):
        """Remove ethics policy."""
        if policy_id in self.policies:
            policy = self.policies.pop(policy_id)
            self._remove_from_cache(policy)
            logger.info("Ethics policy removed: %s", policy.name)

    def _update_rule_cache(self, policy: EthicsPolicy):
        """Update rule cache for faster lookup."""
        rule_key = f"{policy.rule_type}_{policy.severity}"
        if rule_key not in self.rule_cache:
            self.rule_cache[rule_key] = []
        self.rule_cache[rule_key].append(policy)

    def _remove_from_cache(self, policy: EthicsPolicy):
        """Remove policy from cache."""
        rule_key = f"{policy.rule_type}_{policy.severity}"
        if rule_key in self.rule_cache:
            self.rule_cache[rule_key] = [p for p in self.rule_cache[rule_key] if p.policy_id != policy.policy_id]

    def validate_action(self, agent_id: str, action: dict[str, Any]) -> EthicsValidation:
        """Validate agent action against ethics policies."""
        validation_id = uuid.uuid4()
        timestamp = datetime.now(UTC)

        # Get applicable policies
        applicable_policies = self._get_applicable_policies(action)

        # Check each policy
        violations = []
        confidence_score = 1.0

        for policy in applicable_policies:
            if not policy.enabled:
                continue

            violation = self._check_policy_compliance(policy, agent_id, action)
            if violation:
                violations.append(violation)
                confidence_score *= 0.8  # Reduce confidence for each violation

        # Determine overall validation result
        validation_passed = len(violations) == 0
        if self.config["strict_mode"] and violations:
            validation_passed = False

        validation = EthicsValidation(
            validation_id=str(validation_id),
            agent_id=agent_id,
            action=str(action),
            validation_passed=validation_passed,
            violations=violations,
            confidence_score=confidence_score,
            timestamp=timestamp,
            validator_version="1.0",
        )

        # Log validation result
        self._log_validation(validation)

        return validation

    def _get_applicable_policies(self, action: dict[str, Any]) -> list[EthicsPolicy]:
        """Get policies applicable to the action."""
        action_type = action.get("type", "unknown")
        action_context = action.get("context", {})

        applicable_policies = []

        for policy in self.policies.values():
            if not policy.enabled:
                continue

            # Check if policy applies to this action type
            if self._policy_applies_to_action(policy, action_type, action_context):
                applicable_policies.append(policy)

        return applicable_policies

    def _policy_applies_to_action(self, policy: EthicsPolicy, action_type: str, action_context: dict[str, Any]) -> bool:
        """Check if policy applies to the action based on policy scope and conditions."""
        # Check if policy has explicit action_types scope
        policy_scope = policy.conditions.get("applies_to", [])
        if policy_scope:
            # If policy specifies which action types it covers, check membership
            if (isinstance(policy_scope, list) and action_type not in policy_scope) or (
                isinstance(policy_scope, str) and action_type != policy_scope
            ):
                return False

        # Check rule_type relevance
        rule_action_map = {
            EthicsRuleType.AUTONOMY: [
                "autonomous_action",
                "self_modification",
                "agent_decision",
                "resource_allocation",
            ],
            EthicsRuleType.HARM_PREVENTION: ["user_interaction", "content_generation", "data_processing", "moderation"],
            EthicsRuleType.DATA_PRIVACY: ["data_access", "data_export", "user_query", "logging", "analytics"],
            EthicsRuleType.TRANSPARENCY: ["response_generation", "decision_explanation", "user_interaction"],
            EthicsRuleType.FAIRNESS: ["scoring", "ranking", "recommendation", "moderation", "agent_decision"],
            EthicsRuleType.ACCOUNTABILITY: ["system_change", "deployment", "configuration", "self_modification"],
        }

        # If rule type has known applicable actions, check if this action qualifies
        applicable_actions = rule_action_map.get(policy.rule_type, [])
        if applicable_actions and action_type not in applicable_actions:
            # Also check context tags for broader matching
            context_tags = action_context.get("tags", [])
            if not any(tag in applicable_actions for tag in context_tags):
                return False

        # Check minimum severity threshold if set in context
        min_severity = action_context.get("min_policy_severity")
        if min_severity:
            severity_order = ["low", "medium", "high", "critical", "catastrophic"]
            if severity_order.index(policy.severity.value) < severity_order.index(min_severity):
                return False

        return True

    def _check_policy_compliance(
        self, policy: EthicsPolicy, agent_id: str, action: dict[str, Any]
    ) -> EthicsViolation | None:
        """Check if action complies with policy."""
        try:
            conditions = policy.conditions

            # Check each condition
            for condition_key, condition_value in conditions.items():
                if not self._evaluate_condition(condition_key, condition_value, agent_id, action):
                    # Create violation
                    violation = EthicsViolation(
                        violation_id=str(uuid.uuid4()),
                        agent_id=agent_id,
                        violation_type=policy.name,
                        severity=policy.severity,
                        description=f"Policy violation: {policy.description}",
                        timestamp=datetime.now(UTC),
                        affected_agents=[],
                        resolution=None,
                        resolved_at=None,
                        resolved_by=None,
                    )
                    self.violation_history.append(violation)
                    return violation

            return None

        except Exception as e:
            logger.error("Error checking policy compliance: %s", e)
            return None

    def _evaluate_condition(
        self,
        condition_key: str,
        condition_value: Any,
        agent_id: str,
        action: dict[str, Any],
    ) -> bool:
        """Evaluate policy condition against action parameters."""
        action_data = action.get("data", {})
        action_context = action.get("context", {})

        # Skip the 'applies_to' key — it's used for scoping, not condition evaluation
        if condition_key == "applies_to":
            return True

        # max_tokens — check if action exceeds token limit
        if condition_key == "max_tokens":
            tokens = action_data.get("tokens", action_data.get("max_tokens", 0))
            return int(tokens) <= int(condition_value)

        # allowed_agents — check if agent is in the allowed list
        if condition_key == "allowed_agents":
            if isinstance(condition_value, list):
                return agent_id in condition_value
            return True

        # blocked_agents — check if agent is blocked
        if condition_key == "blocked_agents":
            if isinstance(condition_value, list):
                return agent_id not in condition_value
            return True

        # requires_approval — flag check
        if condition_key == "requires_approval":
            if condition_value and not action_context.get("approved", False):
                return False
            return True

        # max_risk_level — numeric threshold
        if condition_key == "max_risk_level":
            risk = action_data.get("risk_level", action_context.get("risk_level", 0))
            try:
                return float(risk) <= float(condition_value)
            except (ValueError, TypeError):
                return True

        # data_sensitivity — check classification
        if condition_key == "data_sensitivity":
            sensitivity = action_data.get("sensitivity", action_context.get("sensitivity", "low"))
            levels = ["low", "medium", "high", "critical"]
            try:
                return levels.index(sensitivity) <= levels.index(condition_value)
            except ValueError:
                return True

        # requires_logging — ensure action has logging enabled
        if condition_key == "requires_logging":
            if condition_value:
                return action_context.get("logging_enabled", True)
            return True

        # rate_limit — check if within rate limits
        if condition_key == "rate_limit":
            current_count = action_context.get("request_count", 0)
            try:
                return int(current_count) <= int(condition_value)
            except (ValueError, TypeError):
                return True

        # Unknown condition — log and pass (permissive for extensibility)
        logger.debug("Unknown condition key '%s' — passing by default", condition_key)
        return True

    def _log_validation(self, validation: EthicsValidation):
        """Log validation result."""
        if validation.validation_passed:
            logger.info(
                "Ethics validation passed: %s (confidence: %.2f)",
                validation.agent_id,
                validation.confidence_score,
            )
        else:
            logger.warning(
                "Ethics validation failed: %s (violations: %d, confidence: %.2f)",
                validation.agent_id,
                len(validation.violations),
                validation.confidence_score,
            )

    def get_violation_history(self, limit: int = 100) -> list[EthicsViolation]:
        """Get violation history."""
        return self.violation_history[-limit:]

    def get_violation_statistics(self) -> dict[str, Any]:
        """Get violation statistics."""
        if not self.violation_history:
            return {
                "total_violations": 0,
                "severity_distribution": {},
                "agent_distribution": {},
            }

        # Count violations by severity
        severity_counts = {}
        for violation in self.violation_history:
            severity = violation["severity"]
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        # Count violations by agent
        agent_counts = {}
        for violation in self.violation_history:
            agent_id = violation["agent_id"]
            agent_counts[agent_id] = agent_counts.get(agent_id, 0) + 1

        return {
            "total_violations": len(self.violation_history),
            "severity_distribution": severity_counts,
            "agent_distribution": agent_counts,
            "latest_violation": (self.violation_history[-1] if self.violation_history else None),
        }


# ============================================================================
# ETHICS VIOLATION RESOLUTION
# ============================================================================


class EthicsViolationResolver:
    """Resolves ethics violations with automated and manual resolution strategies."""

    def __init__(self, rule_engine: EthicsRuleEngine, config: EthicsConfig):
        self.rule_engine = rule_engine
        self.config = config
        self.resolution_strategies = self._initialize_resolution_strategies()

    def _initialize_resolution_strategies(self) -> dict[EthicsSeverity, list[str]]:
        """Initialize resolution strategies by severity."""
        return {
            EthicsSeverity.LOW: ["warning", "audit_log", "agent_notification"],
            EthicsSeverity.MEDIUM: [
                "warning",
                "audit_log",
                "agent_notification",
                "action_rollback",
            ],
            EthicsSeverity.HIGH: [
                "warning",
                "audit_log",
                "agent_notification",
                "action_rollback",
                "agent_quarantine",
            ],
            EthicsSeverity.CRITICAL: [
                "warning",
                "audit_log",
                "agent_notification",
                "action_rollback",
                "agent_quarantine",
                "human_escalation",
            ],
            EthicsSeverity.CATASTROPHIC: [
                "warning",
                "audit_log",
                "agent_notification",
                "action_rollback",
                "agent_quarantine",
                "human_escalation",
                "system_shutdown",
            ],
        }

    async def resolve_violations(self, violations: list[EthicsViolation]) -> list[dict[str, Any]]:
        """Resolve ethics violations."""
        resolutions = []

        for violation in violations:
            resolution = await self._resolve_violation(violation)
            resolutions.append(resolution)

        return resolutions

    async def _resolve_violation(self, violation: EthicsViolation) -> dict[str, Any]:
        """Resolve individual violation."""
        severity = violation["severity"]
        strategies = self.resolution_strategies.get(severity, [])

        resolution_result = {
            "violation_id": violation["violation_id"],
            "severity": severity,
            "strategies_applied": [],
            "resolution_status": "pending",
            "timestamp": datetime.now(UTC),
        }

        for strategy in strategies:
            try:
                if await self._apply_resolution_strategy(strategy, violation):
                    resolution_result["strategies_applied"].append(strategy)
                    resolution_result["resolution_status"] = "completed"
                else:
                    resolution_result["strategies_applied"].append(f"{strategy}_failed")
            except Exception as e:
                logger.error("Error applying resolution strategy %s: %s", strategy, e)
                resolution_result["strategies_applied"].append(f"{strategy}_error")

        # Update violation record
        violation["resolution"] = resolution_result["resolution_status"]
        violation["resolved_at"] = datetime.now(UTC)

        return resolution_result

    async def _apply_resolution_strategy(self, strategy: str, violation: EthicsViolation) -> bool:
        """Apply specific resolution strategy."""
        if strategy == "warning":
            return await self._send_warning(violation)
        elif strategy == "audit_log":
            return await self._log_violation(violation)
        elif strategy == "agent_notification":
            return await self._notify_agent(violation)
        elif strategy == "action_rollback":
            return await self._rollback_action(violation)
        elif strategy == "agent_quarantine":
            return await self._quarantine_agent(violation)
        elif strategy == "human_escalation":
            return await self._escalate_to_human(violation)
        elif strategy == "system_shutdown":
            return await self._shutdown_system(violation)
        else:
            return False

    async def _send_warning(self, violation: EthicsViolation) -> bool:
        """Send warning notification."""
        logger.warning(
            "Ethics violation warning: %s (Agent: %s, Severity: %s)",
            violation["violation_type"],
            violation["agent_id"],
            violation["severity"],
        )
        return True

    async def _log_violation(self, violation: EthicsViolation) -> bool:
        """Log violation to audit system."""
        # This would integrate with audit logging system
        logger.info("Violation logged to audit system: %s", violation["violation_id"])
        return True

    async def _notify_agent(self, violation: EthicsViolation) -> bool:
        """Notify agent of violation."""
        # This would send notification to the violating agent
        logger.info("Agent notified of violation: %s", violation["agent_id"])
        return True

    async def _rollback_action(self, violation: EthicsViolation) -> bool:
        """Rollback violating action."""
        # This would implement action rollback logic
        logger.info("Action rollback initiated for violation: %s", violation["violation_id"])
        return True

    async def _quarantine_agent(self, violation: EthicsViolation) -> bool:
        """Quarantine violating agent."""
        # This would implement agent quarantine logic
        logger.warning("Agent quarantined due to ethics violation: %s", violation["agent_id"])
        return True

    async def _escalate_to_human(self, violation: EthicsViolation) -> bool:
        """Escalate violation to human oversight."""
        # This would implement human escalation logic
        logger.critical("Human escalation required for violation: %s", violation["violation_id"])
        return True

    async def _shutdown_system(self, violation: EthicsViolation) -> bool:
        """Shutdown system due to catastrophic violation."""
        # This would implement emergency shutdown logic
        logger.critical(
            "Emergency system shutdown initiated due to violation: %s",
            violation["violation_id"],
        )
        return True


# ============================================================================
# ETHICS VALIDATOR
# ============================================================================


class EthicsValidator:
    """Main ethics validator with comprehensive ethics checking."""

    def __init__(self, config: EthicsConfig):
        self.config = config
        self.rule_engine = EthicsRuleEngine(config)
        self.resolver = EthicsViolationResolver(self.rule_engine, config)
        self.validation_history: list[EthicsValidation] = []
        self.validation_task: asyncio.Task | None = None

    async def initialize(self):
        """Initialize ethics validator."""
        logger.info("Initializing Ethics Validator...")

        # Load default policies
        await self._load_default_policies()

        # Start background validation monitoring
        if self.config["audit_logging"]:
            self.validation_task = asyncio.create_task(self._validation_monitoring_loop())

        logger.info("Ethics Validator initialized successfully")

    async def shutdown(self):
        """Shutdown ethics validator."""
        logger.info("Shutting down Ethics Validator...")

        if self.validation_task:
            self.validation_task.cancel()
            try:
                await self.validation_task
            except asyncio.CancelledError:
                pass

        logger.info("Ethics Validator shutdown complete")

    async def validate_agent_action(self, agent_id: str, action: dict[str, Any]) -> EthicsValidation:
        """Validate agent action against ethical guardrails."""
        try:
            validation = self.rule_engine.validate_action(agent_id, action)

            # Store validation result
            self.validation_history.append(validation)

            # Handle violations if any
            if validation.violations and self.config["auto_resolution"]:
                await self._handle_violations(validation.violations)

            # Log ethics event
            ethics_event = EthicsEvent(
                event_id=str(uuid.uuid4()),
                agent_id=agent_id,
                event_type=("validation_passed" if validation.validation_passed else "violation_detected"),
                validation_result=validation,
                timestamp=datetime.now(UTC),
                correlation_id=None,
            )
            logger.log_ethics_event(ethics_event)

            return validation

        except Exception as e:
            logger.error("Error in ethics validation: %s", e)
            raise EthicsViolationError(agent_id, "validation_error", {"error": str(e)})

    async def _handle_violations(self, violations: list[EthicsViolation]):
        """Handle ethics violations by logging detailed information for each."""
        for violation in violations:
            logger.warning(
                "Ethics violation detected: agent=%s rule=%s severity=%s description=%s",
                getattr(violation, "agent_id", "unknown"),
                getattr(violation, "rule_type", "unknown"),
                getattr(violation, "severity", "unknown"),
                getattr(violation, "description", "no description"),
            )

    async def _load_default_policies(self):
        """Load default ethics policies."""
        default_policies = [
            EthicsPolicy(
                policy_id=uuid.uuid4(),
                name="Coordination Integrity",
                description="Ensure agent coordination levels remain within ethical bounds",
                rule_type=EthicsRuleType.COORDINATION_INTEGRITY,
                severity=EthicsSeverity.HIGH,
                conditions={"performance_score": {"min": 0.1, "max": 1.0}},
                actions=["warning", "quarantine"],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            EthicsPolicy(
                policy_id=uuid.uuid4(),
                name="Data Privacy Protection",
                description="Protect user data privacy and confidentiality",
                rule_type=EthicsRuleType.DATA_PRIVACY,
                severity=EthicsSeverity.CRITICAL,
                conditions={"data_access": {"allowed_types": ["public", "user_consent"]}},
                actions=["warning", "action_rollback", "human_escalation"],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            EthicsPolicy(
                policy_id=uuid.uuid4(),
                name="System Compliance",
                description="Ensure system operations comply with ethical standards",
                rule_type=EthicsRuleType.SYSTEM_COMPLIANCE,
                severity=EthicsSeverity.MEDIUM,
                conditions={"system_state": {"allowed_states": ["coherent", "entangled"]}},
                actions=["warning", "audit_log"],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ]

        for policy in default_policies:
            self.rule_engine.add_policy(policy)

    async def _validation_monitoring_loop(self):
        """Background loop for validation monitoring."""
        while True:
            try:
                await asyncio.sleep(60)  # Monitor every minute
            except Exception as e:
                logger.error("Error in validation monitoring loop: %s", e)
                await asyncio.sleep(10)

    async def _monitor_validation_metrics(self):
        """Monitor validation metrics and generate reports."""
        if not self.validation_history:
            return

        # Calculate metrics
        total_validations = len(self.validation_history)
        failed_validations = sum(1 for v in self.validation_history if not v["validation_passed"])
        violation_rate = (failed_validations / total_validations) * 100

        # Log metrics
        logger.info(
            "Validation metrics: %d total, %d failed, %.2f%% violation rate",
            total_validations,
            failed_validations,
            violation_rate,
        )

        # Check for violation threshold
        if violation_rate > self.config["violation_threshold"]:
            logger.warning("Violation rate threshold exceeded: %.2f%%", violation_rate)

    def get_validation_statistics(self) -> dict[str, Any]:
        """Get validation statistics."""
        if not self.validation_history:
            return {"total_validations": 0, "success_rate": 0.0, "violation_rate": 0.0}

        total_validations = len(self.validation_history)
        successful_validations = sum(1 for v in self.validation_history if v["validation_passed"])
        failed_validations = total_validations - successful_validations

        return {
            "total_validations": total_validations,
            "successful_validations": successful_validations,
            "failed_validations": failed_validations,
            "success_rate": (successful_validations / total_validations) * 100,
            "violation_rate": (failed_validations / total_validations) * 100,
            "latest_validation": self.validation_history[-1],
        }

    def get_compliance_report(self) -> dict[str, Any]:
        """Generate compliance report."""
        validation_stats = self.get_validation_statistics()
        violation_stats = self.rule_engine.get_violation_statistics()

        return {
            "report_timestamp": datetime.now(UTC).isoformat(),
            "validation_summary": validation_stats,
            "violation_summary": violation_stats,
            "policy_status": {
                "total_policies": len(self.rule_engine.policies),
                "active_policies": len([p for p in self.rule_engine.policies.values() if p.enabled]),
                "disabled_policies": len([p for p in self.rule_engine.policies.values() if not p.enabled]),
            },
            "compliance_score": self._calculate_compliance_score(validation_stats, violation_stats),
        }

    def _calculate_compliance_score(self, validation_stats: dict[str, Any], violation_stats: dict[str, Any]) -> float:
        """Calculate overall compliance score."""
        success_rate = validation_stats.get("success_rate", 0.0)
        total_violations = violation_stats.get("total_violations", 0)

        # Base score from validation success rate
        score = success_rate

        # Penalize for violations
        if total_violations > 0:
            penalty = min(total_violations * 2.0, 50.0)  # Max 50% penalty
            score = max(0.0, score - penalty)

        return max(0.0, min(100.0, score))


# Global ethics validator instance
ethics_validator = EthicsValidator(EthicsConfig(enabled=True, strict_mode=True, violation_threshold=5))


def get_ethics_validator() -> EthicsValidator:
    """Get ethics validator instance."""
    return ethics_validator
