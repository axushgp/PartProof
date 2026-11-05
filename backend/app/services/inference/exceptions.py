class InferenceError(Exception):
    """Base exception for all inference operations."""
    def __init__(self, message: str, status_code: int = 500, model: str = ""):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.model = model


class InferenceAuthError(InferenceError):
    """Raised when inference API authentication fails."""
    def __init__(self, message: str = "Vultr Serverless Inference authentication failed", model: str = ""):
        super().__init__(message, status_code=401, model=model)


class InferenceRateLimitError(InferenceError):
    """Raised when provider rate limits are exceeded."""
    def __init__(self, message: str = "Vultr Serverless Inference rate limit exceeded", model: str = ""):
        super().__init__(message, status_code=429, model=model)


class InferenceTimeoutError(InferenceError):
    """Raised when inference request times out."""
    def __init__(self, message: str = "Vultr Serverless Inference request timed out", model: str = ""):
        super().__init__(message, status_code=504, model=model)


class InferenceProviderError(InferenceError):
    """Raised when provider returns a 5xx or unexpected error."""
    def __init__(self, message: str, status_code: int = 502, model: str = ""):
        super().__init__(message, status_code=status_code, model=model)


class InferenceConfigurationError(InferenceError):
    """Raised when inference credentials or parameters are improperly configured."""
    def __init__(self, message: str = "Vultr Serverless Inference is not configured properly"):
        super().__init__(message, status_code=500)


class TaskPlanningError(InferenceError):
    """Base exception for task planning errors."""
    pass


class PlanValidationError(TaskPlanningError):
    """Raised when model output fails JSON schema or policy validation."""
    def __init__(self, message: str, raw_output: str = "", violations: list = None):
        super().__init__(message, status_code=422)
        self.raw_output = raw_output
        self.violations = violations or []
