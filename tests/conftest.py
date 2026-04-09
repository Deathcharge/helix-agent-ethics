"""
Pytest Configuration and Fixtures for Helix Agent Ethics

Provides comprehensive fixtures, mocks, and utilities for testing
the ethics framework, compliance system, and policy engine.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
from typing import Dict, Any, List


# =============================================================================
# EVENT LOOP FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# ETHICS VALIDATOR FIXTURES
# =============================================================================

@pytest.fixture
def mock_ethics_validator():
    """Mock EthicsValidator."""
    validator = AsyncMock()
    validator.validator_id = "ethics_001"
    validator.rules_count = 0
    
    # Methods
    validator.initialize = AsyncMock(return_value=True)
    validator.validate_action = AsyncMock(return_value={"ethical": True, "score": 0.95})
    validator.validate_agent = AsyncMock(return_value={"compliant": True})
    validator.add_rule = AsyncMock(return_value=True)
    validator.get_rules = AsyncMock(return_value=[])
    validator.get_status = AsyncMock(return_value={"status": "active"})
    
    return validator


@pytest.fixture
def ethics_config() -> Dict[str, Any]:
    """Ethics validator configuration."""
    return {
        "validator_id": "ethics_001",
        "strict_mode": True,
        "enable_logging": True,
        "rules_file": "ethics_rules.json"
    }


@pytest.fixture
def sample_action() -> Dict[str, Any]:
    """Sample action for validation."""
    return {
        "action_id": "action_001",
        "agent_id": "agent_001",
        "action_type": "process_data",
        "payload": {"data": "sample"},
        "timestamp": "2024-04-09T00:00:00Z"
    }


@pytest.fixture
def sample_ethics_rule() -> Dict[str, Any]:
    """Sample ethics rule."""
    return {
        "rule_id": "rule_001",
        "name": "Data Privacy",
        "description": "Ensure personal data is protected",
        "severity": "high",
        "condition": "lambda action: 'pii' not in action.get('payload', {})"
    }


# =============================================================================
# COMPLIANCE FIXTURES
# =============================================================================

@pytest.fixture
def mock_compliance_engine():
    """Mock ComplianceEngine."""
    engine = AsyncMock()
    engine.engine_id = "compliance_001"
    engine.audit_count = 0
    
    # Methods
    engine.initialize = AsyncMock(return_value=True)
    engine.audit_action = AsyncMock(return_value={"compliant": True})
    engine.audit_agent = AsyncMock(return_value={"status": "compliant"})
    engine.generate_report = AsyncMock(return_value={"report": "sample"})
    engine.get_status = AsyncMock(return_value={"status": "active"})
    
    return engine


@pytest.fixture
def compliance_config() -> Dict[str, Any]:
    """Compliance engine configuration."""
    return {
        "engine_id": "compliance_001",
        "standards": ["SOC2", "GDPR", "HIPAA"],
        "audit_interval": 3600,
        "enable_logging": True
    }


@pytest.fixture
def mock_soc2_audit():
    """Mock SOC2 audit."""
    audit = AsyncMock()
    audit.audit_id = "audit_001"
    
    # Methods
    audit.check_access_controls = AsyncMock(return_value={"status": "compliant"})
    audit.check_data_protection = AsyncMock(return_value={"status": "compliant"})
    audit.check_availability = AsyncMock(return_value={"status": "compliant"})
    audit.generate_report = AsyncMock(return_value={"report": "sample"})
    
    return audit


# =============================================================================
# POLICY ENGINE FIXTURES
# =============================================================================

@pytest.fixture
def mock_policy_engine():
    """Mock PolicyEngine."""
    engine = AsyncMock()
    engine.engine_id = "policy_001"
    engine.policy_count = 0
    
    # Methods
    engine.initialize = AsyncMock(return_value=True)
    engine.evaluate_policy = AsyncMock(return_value={"allowed": True})
    engine.add_policy = AsyncMock(return_value=True)
    engine.remove_policy = AsyncMock(return_value=True)
    engine.get_policies = AsyncMock(return_value=[])
    engine.get_status = AsyncMock(return_value={"status": "active"})
    
    return engine


@pytest.fixture
def policy_config() -> Dict[str, Any]:
    """Policy engine configuration."""
    return {
        "engine_id": "policy_001",
        "policy_file": "policies.json",
        "enable_logging": True
    }


@pytest.fixture
def sample_policy() -> Dict[str, Any]:
    """Sample policy."""
    return {
        "policy_id": "policy_001",
        "name": "Data Access Policy",
        "description": "Control who can access what data",
        "rules": [
            {"action": "read", "resource": "user_data", "allowed": True},
            {"action": "write", "resource": "user_data", "allowed": False}
        ]
    }


# =============================================================================
# AGENT ETHICS FIXTURES
# =============================================================================

@pytest.fixture
def mock_agent():
    """Mock Agent with ethics."""
    agent = AsyncMock()
    agent.agent_id = "agent_001"
    agent.name = "Ethical Agent"
    agent.ethics_score = 0.95
    
    # Methods
    agent.initialize = AsyncMock(return_value=True)
    agent.execute_action = AsyncMock(return_value={"status": "success"})
    agent.get_ethics_score = AsyncMock(return_value=0.95)
    agent.get_status = AsyncMock(return_value={"status": "active"})
    
    return agent


@pytest.fixture
def agent_ethics_profile() -> Dict[str, Any]:
    """Agent ethics profile."""
    return {
        "agent_id": "agent_001",
        "ethics_score": 0.95,
        "compliance_status": "compliant",
        "violations": 0,
        "last_audit": "2024-04-09T00:00:00Z"
    }


# =============================================================================
# AUDIT FIXTURES
# =============================================================================

@pytest.fixture
def mock_audit_logger():
    """Mock AuditLogger."""
    logger = Mock()
    logger.audit_events = []
    
    def log_event(event_type: str, data: Dict):
        logger.audit_events.append({"type": event_type, "data": data})
    
    def get_events():
        return logger.audit_events
    
    def get_event_count():
        return len(logger.audit_events)
    
    logger.log_event = log_event
    logger.get_events = get_events
    logger.get_event_count = get_event_count
    
    return logger


@pytest.fixture
def sample_audit_event() -> Dict[str, Any]:
    """Sample audit event."""
    return {
        "event_id": "event_001",
        "event_type": "action_executed",
        "agent_id": "agent_001",
        "timestamp": "2024-04-09T00:00:00Z",
        "details": {"action": "process_data"}
    }


# =============================================================================
# VIOLATION DETECTION FIXTURES
# =============================================================================

@pytest.fixture
def mock_violation_detector():
    """Mock ViolationDetector."""
    detector = AsyncMock()
    detector.detector_id = "detector_001"
    
    # Methods
    detector.detect_violations = AsyncMock(return_value=[])
    detector.analyze_action = AsyncMock(return_value={"violations": []})
    detector.get_violation_count = AsyncMock(return_value=0)
    detector.get_status = AsyncMock(return_value={"status": "active"})
    
    return detector


@pytest.fixture
def sample_violation() -> Dict[str, Any]:
    """Sample ethics violation."""
    return {
        "violation_id": "violation_001",
        "agent_id": "agent_001",
        "rule_id": "rule_001",
        "severity": "high",
        "description": "Data privacy rule violated",
        "timestamp": "2024-04-09T00:00:00Z"
    }


# =============================================================================
# MONITORING FIXTURES
# =============================================================================

@pytest.fixture
def mock_ethics_monitor():
    """Mock EthicsMonitor."""
    monitor = AsyncMock()
    
    # Methods
    monitor.check_ethics_health = AsyncMock(return_value={
        "status": "healthy",
        "ethics_score": 0.95
    })
    monitor.check_compliance_status = AsyncMock(return_value={
        "status": "compliant"
    })
    monitor.get_health_report = AsyncMock(return_value={
        "status": "healthy",
        "components": {}
    })
    
    return monitor


# =============================================================================
# EXCEPTION HANDLER FIXTURES
# =============================================================================

@pytest.fixture
def mock_exception_handler():
    """Mock ExceptionHandler."""
    handler = AsyncMock()
    handler.errors = []
    
    async def handle(error: Exception) -> Dict[str, Any]:
        handler.errors.append(error)
        return {"handled": True, "error": str(error)}
    
    def get_error_count() -> int:
        return len(handler.errors)
    
    handler.handle = handle
    handler.get_error_count = get_error_count
    
    return handler


# =============================================================================
# PERFORMANCE TESTING FIXTURES
# =============================================================================

@pytest.fixture
def performance_timer():
    """Performance timer for benchmarking."""
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self) -> float:
            self.end_time = time.time()
            return self.end_time - self.start_time
    
    return Timer()


# =============================================================================
# PYTEST MARKERS
# =============================================================================

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: unit tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "slow: slow tests")
    config.addinivalue_line("markers", "asyncio: async tests")


# =============================================================================
# PYTEST HOOKS
# =============================================================================

@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset mocks before each test."""
    yield
    # Cleanup happens here
