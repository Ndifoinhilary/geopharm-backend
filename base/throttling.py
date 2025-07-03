from rest_framework.throttling import AnonRateThrottle, UserRateThrottle, SimpleRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Throttle for login attempts to prevent brute force attacks.
    """
    scope = 'login'


class SignupRateThrottle(AnonRateThrottle):
    """
    Throttle for signup attempts to prevent abuse.
    """
    scope = 'signup'


class PasswordResetRateThrottle(AnonRateThrottle):
    """
    Throttle for password reset requests to prevent abuse.
    """
    scope = 'password_reset'


class VerificationCodeThrottle(AnonRateThrottle):
    """
    Throttle for verification code requests to prevent abuse.
    """
    scope = 'verification_code'


class UsernameIPRateThrottle(SimpleRateThrottle):
    """
    Limits the rate of API calls by unique username/IP pairs.
    """
    scope = 'login_username_ip'

    def get_cache_key(self, request, view):
        username = request.data.get('email') or ''
        if not username:
            return None

        ident = f"{username}_{self.get_ident(request)}"
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }