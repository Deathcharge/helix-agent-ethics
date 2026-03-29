"""
Helix Ethics - Enterprise AI Governance & Ethical Decision Framework

A production-grade framework for implementing ethical guardrails in autonomous AI systems.
Provides 4 core ethical principles, compliance tracking, and real-time validation.
"""

__version__ = "1.0.0"
__author__ = "Andrew John Ward"
__license__ = "Apache-2.0"

# Core imports
try:
    from .ethics.ethics_validator import EthicsValidator, EthicsPrinciple, ViolationType
    from .compliance.soc2_audit import ComplianceAuditor
except ImportError as e:
    print(f"Warning: Could not import core modules: {e}")

__all__ = [
    "EthicsValidator",
    "EthicsPrinciple",
    "ViolationType",
    "ComplianceAuditor",
]
