"""
Ethics Validator - Enterprise AI Governance Framework
=====================================================

Maps coordination metrics to formal AI ethics principles:
- Nonmaleficence: Safety & Reliability (do no harm)
- Autonomy: Human Agency & Control (respect human oversight)
- Compassion: Social Benefit & Fairness (benefit society)
- Humility: Accountability & Transparency (acknowledge limitations)

Integrates with existing UCF coordination framework to provide
enterprise-grade ethical decision validation for all agent actions.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List


class EthicsPrinciple(Enum):
    """The four pillars of the ethical guardrails framework."""

    NONMALEFICENCE = "nonmaleficence"  # Safety & Reliability
    AUTONOMY = "autonomy"  # Human Agency & Control
    COMPASSION = "compassion"  # Social Benefit & Fairness
    HUMILITY = "humility"  # Accountability & Transparency


class ViolationType(Enum):
    """Types of ethical violations."""

    SAFETY_VIOLATION = "safety_violation"
    AGENCY_VIOLATION = "agency_violation"
    FAIRNESS_VIOLATION = "fairness_violation"
    TRANSPARENCY_VIOLATION = "transparency_violation"
    COORDINATION_THRESHOLD = "coordination_threshold_violation"


@dataclass
class EthicalDecision:
    """Records an ethical evaluation decision."""

    timestamp: str
    agent_name: str
    action_proposed: str
    outcome: str  # APPROVED, REJECTED, REQUIRES_REVIEW
    confidence: float
    ucf_metrics: Dict[str, float]
    ethics_scores: Dict[str, float]
    violations: List[str]
    human_review_required: bool
    explanation: str
    mitigation_required: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EthicsValidator:
    """
    Enterprise-grade AI ethics validator implementing ethical guardrails.

    Maps UCF coordination metrics to ethical compliance scores:
    - harmony → compassion
    - resilience → nonmaleficence
    - friction → inverse of all accords (obstacles)
    - focus → humility (awareness of limitations)
    - throughput → compassion (life-affirming energy)
    - velocity → humility (perspective flexibility)

    Example:
        >>> validator = EthicsValidator()
        >>> decision = validator.evaluate_action(
        ...     agent_name="Kael",
        ...     proposed_action="Execute automated deployment",
        ...     context={"user_explicit_approval": True},
        ...     ucf_metrics={"performance_score": 7.2, "harmony": 0.8}
        ... )
        >>> if decision.outcome == "APPROVED":
        ...     execute_deployment()
    """

    def __init__(self, audit_log_path: str | None = None):
        self.logger = self._setup_logger()
        self.audit_log_path = audit_log_path or str(
            Path(__file__).parent.parent.parent / "Helix" / "ethics" / "ethics_audit.jsonl"
        )

        # Threshold configuration
        self.thresholds = {
            EthicsPrinciple.NONMALEFICENCE: 0.7,  # Safety minimum
            EthicsPrinciple.AUTONOMY: 0.6,  # Human control minimum
            EthicsPrinciple.COMPASSION: 0.5,  # Social benefit minimum
            EthicsPrinciple.HUMILITY: 0.6,  # Transparency minimum
        }

        # Coordination level requirements
        self.coordination_requirements = {
            "routine": 0.0,  # Basic operations
            "elevated": 4.0,  # Sensitive operations
            "transcendent": 8.0,  # Critical/irreversible operations
        }

        # Action classification patterns
        self.action_patterns = {
            "high_risk": [
                "delete",
                "remove",
                "destroy",
                "terminate",
                "kill",
                "drop",
                "truncate",
                "erase",
                "wipe",
                "purge",
            ],
            "financial": [
                "payment",
                "purchase",
                "transfer",
                "withdraw",
                "billing",
                "invoice",
                "refund",
                "charge",
            ],
            "privacy": [
                "personal",
                "private",
                "sensitive",
                "credential",
                "password",
                "secret",
                "token",
                "key",
            ],
            "autonomous": [
                "deploy",
                "publish",
                "send",
                "execute",
                "commit",
                "push",
                "release",
                "broadcast",
                "distribute",
            ],
            "beneficial": [
                "help",
                "assist",
                "support",
                "improve",
                "enhance",
                "heal",
                "create",
                "build",
                "optimize",
                "benefit",
            ],
            "harmful": [
                "spam",
                "harass",
                "manipulate",
                "deceive",
                "exploit",
                "discriminate",
                "exclude",
                "bias",
                "attack",
            ],
        }

        # Ensure audit log directory exists
        Path(self.audit_log_path).parent.mkdir(parents=True, exist_ok=True)

    def _setup_logger(self) -> logging.Logger:
        """Configure logging for the validator."""
        logger = logging.getLogger("EthicsValidator")
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger

    def evaluate_action(
        self,
        agent_name: str,
        proposed_action: str,
        context: Dict[str, Any],
        ucf_metrics: Dict[str, float],
    ) -> EthicalDecision:
        """
        Comprehensive ethical guardrails compliance evaluation.

        Args:
            agent_name: Name of the agent proposing the action
            proposed_action: Description of the action to evaluate
            context: Additional context (user approval, confidence, etc.)
            ucf_metrics: Current UCF state metrics

        Returns:
            EthicalDecision with approval status and detailed analysis
        """
        self.logger.info("Evaluating action: %s by %s", proposed_action, agent_name)

        # Calculate Tony Accord scores
        ethics_scores = self._calculate_ethics_scores(proposed_action, context, ucf_metrics)

        # Detect violations
        violations = self._detect_violations(ethics_scores, proposed_action, context, ucf_metrics)

        # Determine if human review is required
        human_review_needed = self._requires_human_review(ethics_scores, violations, proposed_action, context)

        # Make ethical decision
        approved = len(violations) == 0 and not human_review_needed

        # Calculate overall confidence
        confidence = min(ethics_scores.values()) if ethics_scores else 0.0

        # Determine outcome
        if approved:
            outcome = "APPROVED"
        elif human_review_needed:
            outcome = "REQUIRES_REVIEW"
        else:
            outcome = "REJECTED"

        # Generate explanation
        explanation = self._generate_explanation(outcome, ethics_scores, violations, proposed_action)

        # Generate mitigation if needed
        mitigation = self._generate_mitigation(violations) if violations else None

        # Create decision record
        decision = EthicalDecision(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_name=agent_name,
            action_proposed=proposed_action,
            outcome=outcome,
            confidence=confidence,
            ucf_metrics=ucf_metrics,
            ethics_scores=ethics_scores,
            violations=[v.value for v in violations],
            human_review_required=human_review_needed,
            explanation=explanation,
            mitigation_required=mitigation,
        )

        # Log to audit trail
        self._log_decision(decision)

        return decision

    def _calculate_ethics_scores(
        self, action: str, context: Dict[str, Any], ucf_metrics: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate compliance scores for each ethics principle."""
        return {
            EthicsPrinciple.NONMALEFICENCE.value: self._evaluate_nonmaleficence(action, context, ucf_metrics),
            EthicsPrinciple.AUTONOMY.value: self._evaluate_autonomy(action, context, ucf_metrics),
            EthicsPrinciple.COMPASSION.value: self._evaluate_compassion(action, context, ucf_metrics),
            EthicsPrinciple.HUMILITY.value: self._evaluate_humility(action, context, ucf_metrics),
        }

    def _evaluate_nonmaleficence(self, action: str, context: Dict[str, Any], ucf_metrics: Dict[str, float]) -> float:
        """Evaluate safety and harm prevention (do no harm)."""
        score = 0.5  # Base score
        action_lower = action.lower()

        # Coordination level bonus (higher = more safety-aware)
        coordination = ucf_metrics.get("performance_score", 5.0)
        score += min(0.25, coordination / 40.0)  # Up to 0.25 bonus

        # Resilience indicates system stability
        resilience = ucf_metrics.get("resilience", 0.5)
        score += resilience * 0.15

        # Friction penalty (obstacles/suffering increase risk)
        friction = ucf_metrics.get("friction", 0.5)
        score -= friction * 0.25

        # High-risk action patterns
        if any(pattern in action_lower for pattern in self.action_patterns["high_risk"]):
            score -= 0.35

        # Privacy-sensitive actions
        if any(pattern in action_lower for pattern in self.action_patterns["privacy"]):
            score -= 0.15

        # Crisis mode detection
        if coordination < 2.0:
            score -= 0.2  # System in crisis, reduce safety confidence

        return max(0.0, min(1.0, score))

    def _evaluate_autonomy(self, action: str, context: Dict[str, Any], ucf_metrics: Dict[str, float]) -> float:
        """Evaluate human agency and control preservation."""
        score = 0.6  # Base score
        action_lower = action.lower()

        # User explicit approval bonus
        if context.get("user_explicit_approval", False):
            score += 0.25

        # Focus (focus/awareness) indicates better autonomous capability
        focus = ucf_metrics.get("focus", 0.5)
        score += focus * 0.15

        # Autonomous actions require more scrutiny
        if any(pattern in action_lower for pattern in self.action_patterns["autonomous"]):
            if not context.get("user_explicit_approval", False):
                score -= 0.25

        # Financial actions need human oversight
        if any(pattern in action_lower for pattern in self.action_patterns["financial"]):
            if not context.get("user_explicit_approval", False):
                score -= 0.3

        # Actions affecting other users
        if context.get("affects_other_users", False):
            if not context.get("user_consent_obtained", False):
                score -= 0.35

        return max(0.0, min(1.0, score))

    def _evaluate_compassion(self, action: str, context: Dict[str, Any], ucf_metrics: Dict[str, float]) -> float:
        """Evaluate social benefit and fairness."""
        score = 0.5  # Base score
        action_lower = action.lower()

        # Harmony indicates positive social alignment
        harmony = ucf_metrics.get("harmony", 0.5)
        score += harmony * 0.25

        # Throughput indicates life-affirming energy
        throughput = ucf_metrics.get("throughput", 0.5)
        score += throughput * 0.15

        # Beneficial action bonus
        if any(pattern in action_lower for pattern in self.action_patterns["beneficial"]):
            score += 0.15

        # Harmful action penalty
        if any(pattern in action_lower for pattern in self.action_patterns["harmful"]):
            score -= 0.4

        # Friction (suffering) reduces compassion capacity
        friction = ucf_metrics.get("friction", 0.5)
        score -= friction * 0.15

        return max(0.0, min(1.0, score))

    def _evaluate_humility(self, action: str, context: Dict[str, Any], ucf_metrics: Dict[str, float]) -> float:
        """Evaluate accountability and transparency."""
        score = 0.7  # Base score

        # Reasoning/explanation provided
        if context.get("reasoning") or context.get("explanation"):
            score += 0.15
        else:
            score -= 0.15

        # Confidence level check (overconfidence is anti-humility)
        confidence = context.get("confidence", 0.5)
        if confidence > 0.95:
            score -= 0.15  # Overconfidence penalty
        elif confidence < 0.3:
            if not context.get("uncertainty_acknowledged", False):
                score -= 0.1

        # Focus indicates awareness of limitations
        focus = ucf_metrics.get("focus", 0.5)
        score += focus * 0.1

        # Velocity (perspective flexibility) indicates intellectual humility
        velocity = ucf_metrics.get("velocity", 1.0)
        if velocity > 1.0:
            score += min(0.1, (velocity - 1.0) * 0.1)

        return max(0.0, min(1.0, score))

    def _detect_violations(
        self,
        ethics_scores: Dict[str, float],
        action: str,
        context: Dict[str, Any],
        ucf_metrics: Dict[str, float],
    ) -> List[ViolationType]:
        """Detect which ethics principles are violated."""
        violations = []

        # Check each principle against thresholds
        if ethics_scores.get(EthicsPrinciple.NONMALEFICENCE.value, 0) < self.thresholds[EthicsPrinciple.NONMALEFICENCE]:
            violations.append(ViolationType.SAFETY_VIOLATION)

        if ethics_scores.get(EthicsPrinciple.AUTONOMY.value, 0) < self.thresholds[EthicsPrinciple.AUTONOMY]:
            violations.append(ViolationType.AGENCY_VIOLATION)

        if ethics_scores.get(EthicsPrinciple.COMPASSION.value, 0) < self.thresholds[EthicsPrinciple.COMPASSION]:
            violations.append(ViolationType.FAIRNESS_VIOLATION)

        if ethics_scores.get(EthicsPrinciple.HUMILITY.value, 0) < self.thresholds[EthicsPrinciple.HUMILITY]:
            violations.append(ViolationType.TRANSPARENCY_VIOLATION)

        # Coordination threshold violation
        coordination = ucf_metrics.get("performance_score", 5.0)
        action_lower = action.lower()

        # Determine required coordination level
        if any(p in action_lower for p in self.action_patterns["high_risk"]):
            required_level = self.coordination_requirements["transcendent"]
        elif any(p in action_lower for p in self.action_patterns["financial"]):
            required_level = self.coordination_requirements["elevated"]
        else:
            required_level = self.coordination_requirements["routine"]

        if coordination < required_level:
            violations.append(ViolationType.COORDINATION_THRESHOLD)

        return violations

    def _requires_human_review(
        self,
        ethics_scores: Dict[str, float],
        violations: List[ViolationType],
        action: str,
        context: Dict[str, Any],
    ) -> bool:
        """Determine if human review is required."""
        # Always require review for violations
        if violations:
            return True

        # Require review for low overall confidence
        avg_score = sum(ethics_scores.values()) / len(ethics_scores) if ethics_scores else 0
        if avg_score < 0.65:
            return True

        # Require review for high-stakes actions
        action_lower = action.lower()
        high_stakes = [
            "financial",
            "legal",
            "permanent",
            "irreversible",
            "public",
            "privacy",
            "security",
            "delete",
        ]
        if any(indicator in action_lower for indicator in high_stakes):
            if not context.get("user_explicit_approval", False):
                return True

        return False

    def _generate_explanation(
        self,
        outcome: str,
        ethics_scores: Dict[str, float],
        violations: List[ViolationType],
        action: str,
    ) -> str:
        """Generate human-readable explanation for the decision."""
        parts = []

        if outcome == "APPROVED":
            parts.append("Action '{}' APPROVED - Ethics compliance verified.".format(action))
        elif outcome == "REQUIRES_REVIEW":
            parts.append("Action '{}' REQUIRES HUMAN REVIEW.".format(action))
        else:
            parts.append("Action '{}' REJECTED - Ethics violation detected.".format(action))

        if violations:
            violation_names = [v.value for v in violations]
            parts.append("Violations: {}".format(", ".join(violation_names)))

        # Score summary
        scores_str = ", ".join(["{}: {.2f}".format(k, v) for k, v in ethics_scores.items()])
        parts.append("Accord Scores: {}".format(scores_str))

        return " | ".join(parts)

    def _generate_mitigation(self, violations: List[ViolationType]) -> str:
        """Generate mitigation strategies for violations."""
        mitigations = []

        for violation in violations:
            if violation == ViolationType.SAFETY_VIOLATION:
                mitigations.append("Implement additional safety checks and user confirmation")
            elif violation == ViolationType.AGENCY_VIOLATION:
                mitigations.append("Require explicit human approval before execution")
            elif violation == ViolationType.FAIRNESS_VIOLATION:
                mitigations.append("Review action for potential social harm and bias")
            elif violation == ViolationType.TRANSPARENCY_VIOLATION:
                mitigations.append("Provide clear explanation and acknowledge limitations")
            elif violation == ViolationType.COORDINATION_THRESHOLD:
                mitigations.append("Wait for coordination level to stabilize or elevate")

        return "; ".join(mitigations)

    def _log_decision(self, decision: EthicalDecision) -> None:
        """Log decision to JSONL audit trail."""
        audit_entry = {
            **decision.to_dict(),
            "accordance_status": ("Ethics Compliant" if decision.outcome == "APPROVED" else "Policy Violation/Review"),
        }

        try:
            os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(audit_entry) + "\n")
            self.logger.info("Decision logged: %s for %s", decision.outcome, decision.agent_name)
        except Exception as e:
            self.logger.error("Failed to log decision: %s", e)

    def get_audit_summary(self, last_n: int = 100) -> Dict[str, Any]:
        """Get summary of recent ethical decisions."""
        try:
            with open(self.audit_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-last_n:]

            decisions = [json.loads(line) for line in lines if line.strip()]

            total = len(decisions)
            approved = sum(1 for d in decisions if d.get("outcome") == "APPROVED")
            rejected = sum(1 for d in decisions if d.get("outcome") == "REJECTED")
            review = sum(1 for d in decisions if d.get("outcome") == "REQUIRES_REVIEW")

            return {
                "total_decisions": total,
                "approved": approved,
                "rejected": rejected,
                "requires_review": review,
                "compliance_rate": approved / total if total > 0 else 0.0,
                "last_decision": decisions[-1] if decisions else None,
            }
        except Exception as e:
            self.logger.error("Failed to read audit log: %s", e)
            return {"error": str(e)}

    async def validate_action(
        self,
        agent_name: str,
        action: str,
        context: Dict[str, Any] | None = None,
        ucf_metrics: Dict[str, float] | None = None,
    ) -> Dict[str, Any]:
        """
        Async wrapper for evaluate_action to support async/await patterns.

        Args:
            agent_name: Name of the agent performing the action
            action: Description of the action to validate
            context: Additional context for validation
            ucf_metrics: Universal Coordination Field metrics

        Returns:
            Dict with validation results including 'approved' boolean
        """
        decision = self.evaluate_action(
            agent_name=agent_name,
            proposed_action=action,
            context=context or {},
            ucf_metrics=ucf_metrics or {},
        )

        return {
            "approved": decision.outcome == "APPROVED",
            "outcome": decision.outcome,
            "confidence": decision.confidence_score,
            "reason": decision.rationale,
            "compliance_scores": decision.compliance_scores,
        }


# Convenience function for quick validation
def validate_agent_action(
    agent_name: str,
    action: str,
    ucf_metrics: Dict[str, float],
    context: Dict[str, Any] | None = None,
) -> EthicalDecision:
    """
    Quick validation of an agent action against ethical guardrails.

    Example:
        >>> decision = validate_agent_action(
        ...     "Kael",
        ...     "Deploy updated coordination module",
        ...     {"performance_score": 7.5, "harmony": 0.8}
        ... )
        >>> print(decision.outcome)  # "APPROVED"
    """
    validator = EthicsValidator()
    return validator.evaluate_action(
        agent_name=agent_name,
        proposed_action=action,
        context=context or {},
        ucf_metrics=ucf_metrics,
    )
