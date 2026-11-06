class PolicyError(Exception):
    """Base exception for deterministic policy engine errors."""
    def __init__(self, message: str, violations: list = None):
        super().__init__(message)
        self.message = message
        self.violations = violations or []


class PolicyDeniedError(PolicyError):
    """Raised when an operation is denied by security policy."""
    pass


class InvalidCapabilityError(PolicyError):
    """Raised when a plan requests unsupported or unallowlisted capabilities."""
    pass


class ResourceLimitExceededError(PolicyError):
    """Raised when plan requests exceed server-enforced resource limits."""
    pass
