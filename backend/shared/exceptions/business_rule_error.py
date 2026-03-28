"""Business Rule Error base class.

Platform-level exception for business rule violations.
Domain layers define specific subclasses (e.g., DivisionByZeroError).
Middleware catches this base class generically and returns HTTP 400.
"""


class BusinessRuleError(Exception):
    """Base exception for all business rule violations.

    Attributes:
        error_code: Machine-readable error code for the HTTP response.
            Subclasses set this to a specific value (e.g., "DIVISION_BY_ZERO").
        message: Human-readable error description.

    AOP Propagation Path:
        Domain (raises) → @observe (logs/metrics/traces) → Handler (no catch) → @api_gateway_handler (HTTP 400)
    """

    error_code: str = "BUSINESS_RULE_ERROR"

    def __init__(self, message: str, error_code: str = None) -> None:
        super().__init__(message)
        if error_code:
            self.error_code = error_code
