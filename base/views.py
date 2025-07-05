import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import cache, timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, permissions
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Profile
from .serializers import RegisterSerializer, VerifyUserSerializer, \
    LoginSerializer, ResendVerificationCodeSerializer, ResetPasswordSerializer, ChangePasswordSerializer, \
    ChangeEmailSerializer, UpdateUserDetailsSerializer
from .throttling import VerificationCodeThrottle, UsernameIPRateThrottle, LoginRateThrottle, \
    PasswordResetRateThrottle, SignupRateThrottle
from .utils import generate_otp_code, send_email_with_template

logger = logging.getLogger(__name__)

User = get_user_model()


class RegisterAPIView(GenericAPIView):
    """
    API view for user registration.
    """
    serializer_class = RegisterSerializer
    throttle_classes = [SignupRateThrottle]

    @swagger_auto_schema(
        operation_description="API for user registration. ",
        responses={
            200: openapi.Response("Account created successfully"),
            400: openapi.Response("Invalid token or email"),
            429: openapi.Response("Too many requests, please try again later"),

        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                password = serializer.validated_data['password']
                user = serializer.save()
                user.set_password(password)

                if not user.otp_code:
                    user.generate_new_otp_code()

                user.save()
            data = {
                "subject": "Verify your email",
            }
            context = {
                "email": user.email,
                "token": user.otp_code,
                "username": user.username,
                "expiration": user.otp_expiry,
                "app_name": "GeoPharm",
                "verification_link": settings.FRONTEND_URL + reverse('verify-user'),
            }
            send_email_with_template(data, 'welcome.html', context, [user.email])
            return Response({
                "Message": "Successfully registered. Please check your email for verification code "
                           "and go ahead and verify your email.",
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class VerifyUserAPIView(GenericAPIView):
    """
    API view for verifying user email using a verification token.
    """
    serializer_class = VerifyUserSerializer

    @swagger_auto_schema(
        operation_description="API for verifying user email using "
                              "a verification code to sent to your email.",
        responses={
            200: openapi.Response("User verified successfully"),
            400: openapi.Response("Invalid token or email"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({
            "message": "User verified successfully. You can now log in.",
        }, status=status.HTTP_200_OK)


class LoginAPIView(GenericAPIView):
    """
    API view for user login.
    """
    serializer_class = LoginSerializer
    throttle_classes = [LoginRateThrottle, UsernameIPRateThrottle]

    @swagger_auto_schema(
        operation_description="API for user login. ",
        responses={
            200: openapi.Response("User login successfully"),
            400: openapi.Response("Invalid credentials or user not verified"),
            403: openapi.Response("Account locked due to too many failed attempts"),
            429: openapi.Response("Too many login attempts, please try again later"),

        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email)

            if user.is_locked():
                return Response({
                    "message": "Account temporarily locked due to too many failed login attempts. Try again later.",
                    "locked_until": f"{settings.LOCK_UNTIL // 60} minutes"
                }, status=status.HTTP_403_FORBIDDEN)

            if not user.is_verified:
                return Response({
                    "message": "User is not verified. Please verify your email first.",
                }, status=status.HTTP_403_FORBIDDEN)

            if serializer.validated_data.get('authenticated', False):
                user.reset_login_attempts()

                token = RefreshToken.for_user(user)
                access_token = token.access_token
                return Response({
                    "message": "Successfully logged in",
                    "email": email,
                    "access_token": str(access_token),
                    "refresh_token": str(token),
                }, status=status.HTTP_200_OK)
            else:
                user.increment_login_attempts()
                return Response({
                    "message": "Invalid credentials",
                }, status=status.HTTP_400_BAD_REQUEST)

        except User.DoesNotExist:
            return Response({
                "message": "Invalid credentials",
            }, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordAPIView(GenericAPIView):
    """
    API view for requesting a password reset.
    You must be authenticated to change your password.
    """
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="API for changing user password. "
                              "You must be authenticated to change your password.",
        responses={
            200: openapi.Response("New code or token send successfully"),
            400: openapi.Response("Invalid  email"),
        }
    )
    def post(self, request, *args, **kwargs):
        """
          Handle password change request and the user must be login to carry out this request.
        :param request:
        :param args:
        :param kwargs:
        :return: updated user password in the system
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        new_password = serializer.validated_data['new_password']
        user.set_password(new_password)
        user.save()
        return Response({
            "message": "Password changed successfully",
            "email": user.email
        }, status=status.HTTP_200_OK)


class ResetPasswordAPIView(GenericAPIView):
    """
    API view for resetting the user's password using a reset token.
    """
    serializer_class = ResetPasswordSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    @swagger_auto_schema(
        operation_description="Reset user password with token",
        responses={
            200: openapi.Response("Password reset successfully"),
            400: openapi.Response("Invalid token or password validation failed"),
            429: openapi.Response("Too many requests, please try again later"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save()

        return Response({
            "message": "Password reset successfully"
        }, status=status.HTTP_200_OK)


class ResendVerificationCodeAPIView(GenericAPIView):
    """
    API view for resending the verification code to the user's email.
    """
    serializer_class = ResendVerificationCodeSerializer
    throttle_classes = [VerificationCodeThrottle]

    @swagger_auto_schema(
        operation_description="Resend verification code to user's email",
        responses={
            200: openapi.Response("Verification code resent successfully"),
            400: openapi.Response("Invalid email or user not found"),
            429: openapi.Response("Too many requests, please try again later"),
        }
    )
    def post(self, request, *args, **kwargs):
        """
        Resend verification code to the user's email.
        :param request: The HTTP request containing the email.
        :return: A response indicating the success or failure of the operation.
        200: openapi.Response("Verification code resent successfully"),
        400: openapi.Response("Invalid email or user not found"),
        """
        ip_address = request.META.get('REMOTE_ADDR')
        cache_key = f"forgot_password_{ip_address}"

        if cache.get(cache_key):
            return Response({
                "error": "Too many requests. Please try again later."
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        cache.set(cache_key, True, timeout=60)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = User.objects.get(email=email)
        user.otp_code = generate_otp_code()
        user.otp_expiry = timezone.now() + timedelta(minutes=10)
        user.save(update_fields=['otp_code', 'otp_expiry'])
        data = {
            "subject": "Resend verification code",

        }
        context = {
            "email": user.email,
            "token": user.otp_code,
            "username": user.full_name,
            "expiration": user.otp_expiry,
            "app_name": "Estate Exchange",
            "verification_link": settings.FRONTEND_URL + reverse('verify-user'),
        }
        send_email_with_template(data, 'welcome.html', context, [user.email])
        return Response({
            "message": "Verification code resent successfully."
        }, status=status.HTTP_200_OK)


class ChangeEmailAPIView(GenericAPIView):
    """
    API view for changing the user's email.
    You must be authenticated to change your email.
    """
    serializer_class = ChangeEmailSerializer
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="API for changing user email. "
                              "You must be authenticated to change your email.",
        responses={
            200: openapi.Response("Email changed successfully"),
            400: openapi.Response("Invalid email or user not found"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.email = serializer.validated_data['new_email']
        user.save()
        data = {
            "subject": "Email Change Notification",
        }
        context = {
            "email": user.email,
            "username": user.full_name,
            "app_name": "GeoPharm",
        }

        send_email_with_template(data, 'change-email.html', context, [user.email])
        return Response({
            "message": "Email changed successfully",
            "email": user.email
        }, status=status.HTTP_200_OK)


class LogoutAPIView(GenericAPIView):
    """
    API view for user logout.
    You must be authenticated to log out.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="API for user logout. You must be authenticated to log out.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'refresh_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='JWT refresh token to blacklist',
                    example='eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'
                ),
            },
            required=['refresh_token']
        ),
        responses={
            200: openapi.Response("Successfully logged out"),
            401: openapi.Response("Authentication credentials were not provided"),
        }
    )
    def post(self, request, *args, **kwargs):
        try:
            refresh_token = request.data.get("refresh_token")

            if not refresh_token:
                return Response({"message": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)

            token = RefreshToken(refresh_token)
            token.blacklist()

            logger.info(f"User {request.user.email} logged out successfully")

            return Response({"message": "Successfully logged out"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            return Response({"message": "Invalid token or token already blacklisted"},
                            status=status.HTTP_400_BAD_REQUEST)


class CurrentUserAPIView(GenericAPIView):
    """
    API view to get the current authenticated user's details.
    You must be authenticated to access this view.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UpdateUserDetailsSerializer
    parser_classes = [FormParser, MultiPartParser]

    @swagger_auto_schema(
        operation_description="Get current authenticated user details or Get your profile details",
        responses={
            200: openapi.Response("Current user details retrieved successfully"),
            401: openapi.Response("Authentication credentials were not provided"),
        }
    )
    def get(self, request, *args, **kwargs):
        user = request.user
        profile = getattr(user, 'profile', None)

        if not profile:
            profile = Profile.objects.create(user=user)

        serializer = self.get_serializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Update current authenticated user details. update your profile details",
        manual_parameters=[
            openapi.Parameter(
                'profile_image',
                openapi.IN_FORM,
                description="Profile image file",
                type=openapi.TYPE_FILE,
                required=False
            )
        ],
        responses={
            200: openapi.Response("User details updated successfully"),
            400: openapi.Response("Invalid data provided"),
            401: openapi.Response("Authentication credentials were not provided"),
        }
    )
    def patch(self, request, *args, **kwargs):
        user = request.user

        profile = getattr(user, 'profile', None)

        if not profile:
            profile = Profile.objects.create(user=user)

        serializer = UpdateUserDetailsSerializer(profile, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'User details updated successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
