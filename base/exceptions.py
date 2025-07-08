"""
Custom exception handlers and business logic error class
"""

import logging

from rest_framework.views import exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns consistent error responses
    """
    response = exception_handler(exc, context)

    if response is not None:
        # Handle JWT authentication errors specifically
        if isinstance(exc, (InvalidToken, TokenError)):
            custom_response_data = {
                'error': True,
                'message': 'Authentication failed',
                'details': {
                    'detail': str(exc),
                    'code': 'authentication_failed'
                },
                'status_code': response.status_code
            }
        else:
            custom_response_data = {
                'error': True,
                'message': 'An error occurred',
                'details': response.data,
                'status_code': response.status_code
            }

        if not isinstance(exc, (InvalidToken, TokenError)):
            logger.error(f"API Exception: {exc}", exc_info=True)

        response.data = custom_response_data

    return response


class BusinessLogicError(Exception):
    """Custom exception for business logic errors"""

    def __init__(self, message, code=None):
        self.message = message
        self.code = code
        super().__init__(self.message)