"""
Helix Ethics Module
===================

Enterprise-grade AI ethics and safety systems for the Helix Coordination Empire.

Components:
- EthicsValidator: Formal ethical framework for agent decision validation
- Enhanced Kavach: Memory injection and command pattern detection (../enhanced_kavach.py)
- Coordination Code Guardian: Coordination-gated code modifications (../coordination_code_guardian.py)

The Ethical Guardrails framework implements four core principles:
1. Nonmaleficence - Safety & Reliability (do no harm)
2. Autonomy - Human Agency & Control (respect human oversight)
3. Compassion - Social Benefit & Fairness (benefit society)
4. Humility - Accountability & Transparency (acknowledge limitations)

Example:
    >>> from ethics import EthicsValidator, validate_agent_action
    >>>
    >>> # Quick validation
    >>> decision = validate_agent_action(
    ...     agent_name="Kael",
    ...     action="Execute deployment",
    ...     ucf_metrics={"performance_score": 7.5, "harmony": 0.8}
    ... )
    >>>
    >>> if decision.outcome == "APPROVED":
    ...     execute_action()
    >>> elif decision.outcome == "REQUIRES_REVIEW":
    ...     queue_for_human_review(decision)
"""

from .ethics_validator import (
    EthicalDecision,
    EthicsPrinciple,
    EthicsValidator,
    ViolationType,
    validate_agent_action,
)

__all__ = [
    "EthicalDecision",
    "EthicsPrinciple",
    "EthicsValidator",
    "ViolationType",
    "validate_agent_action",
]
