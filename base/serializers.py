import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.translation import gettext as _
from rest_framework import serializers

from .models import User, Profile
from .utils import generate_otp_code, validate_password_strength, send_email_with_template

logger = logging.getLogger(__name__)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'username', 'password', 'confirm_password']

    def validate_password(self, value):
        validate_password_strength(value)
        return value

    def validate(self, data):
        password = data['password']
        confirm_password = data.pop('confirm_password')
        if password != confirm_password:
            raise serializers.ValidationError('Passwords do not match')

        if User.objects.filter(email=data['email']).exists():
            raise serializers.ValidationError('Email already registered')
        return data


class VerifyUserSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(write_only=True, required=True)

    def validate(self, data):
        token = data['token']
        email = data['email']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError('Invalid email or token')

        try:
            user.verify_user(token)
        except ValueError as e:
            error_message = str(e)

            if "expired" in error_message.lower() and not user.is_verified:
                user.otp_code = generate_otp_code()
                user.otp_expiry = timezone.now() + timedelta(minutes=15)
                user.save(update_fields=['otp_code', 'otp_expiry'])
                data = {
                    "subject": "New verification code",

                }
                context = {
                    "email": user.email,
                    "token": user.otp_code,
                    "username": user.username,
                    "expiration": user.otp_expiry,
                    "app_name": "ResolveMeQ",
                    "verification_link": settings.FRONTEND_URL + reverse('verify-user'),
                }
                send_email_with_template(data, 'welcome.html', context, [user.email])
                # TODO: Replace with your email sending function
                error_message += " A new verification code has been sent."

            raise serializers.ValidationError(error_message)

        return data


class SignInSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            raise serializers.ValidationError("Must include 'email' and 'password'.")

        # Try to authenticate the user
        user = authenticate(email=email, password=password)

        if not user:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")

        if not user.is_verified:
            raise serializers.ValidationError("Please verify your email before logging in.")

        data['user'] = user
        return data


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        try:
            user = User.objects.get(email=email)
            if user.check_password(password):
                attrs['authenticated'] = True
            else:
                attrs['authenticated'] = False
        except User.DoesNotExist:
            attrs['authenticated'] = False

        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate_new_password(self, value):
        """
        Validate that the new password meets the requirements.
        :param value: new_password
        :return: new_password
        """
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long")
        return value

    def validate(self, data):
        """
        Validate that the old password is correct and new passwords match.
        :param data:
        :return: validated data
        """
        user = self.context['request'].user
        old_password = data['old_password']
        new_password = data['new_password']
        confirm_password = data['confirm_password']

        if not user.check_password(old_password):
            raise serializers.ValidationError("Old password is incorrect")

        if not constant_time_compare(new_password, confirm_password):
            raise serializers.ValidationError("New passwords do not match")

        if constant_time_compare(old_password, new_password):
            raise serializers.ValidationError("Old password cannot be the same as new password")

        return data


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate_new_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long")
        return value

    def validate(self, data):
        if not constant_time_compare(str(data['new_password']), str(data['confirm_password'])):
            raise serializers.ValidationError("Passwords do not match")

        email = data['email']
        token = data['token']

        try:
            user = User.objects.get(email=email)

            if not user.secure_code or not constant_time_compare(str(user.secure_code), str(token)):
                raise serializers.ValidationError("Invalid or expired reset token")

            if user.secure_code_expiry and user.secure_code_expiry < timezone.now():
                raise serializers.ValidationError("Reset token has expired")

        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid reset token")

        return data

    def save(self, **kwargs):
        email = self.validated_data['email']
        new_password = self.validated_data['new_password']
        token = self.validated_data['token']

        try:
            user = User.objects.get(email=email)

            if (user.otp_code and
                    constant_time_compare(str(user.otp_code), str(token)) and
                    user.otp_expiry and
                    user.otp_expiry >= timezone.now()):

                user.set_password(new_password)

                user.otp_code = None
                user.otp_expiry = None

                user.save(update_fields=['password', 'otp_code', 'otp_expiry'])

            else:
                raise serializers.ValidationError("Invalid or expired reset token")

        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid reset token")


class ResendVerificationCodeSerializer(serializers.Serializer):
    """
    Serializer for resending verification code to the user.
    """
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        """
        Validate that the email exists and is not verified.
        """
        try:
            user = User.objects.get(email=value)
            if user.is_verified:
                raise serializers.ValidationError("User is already verified")
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist")
        return value


class ChangeEmailSerializer(serializers.Serializer):
    """
    Serializer for changing user email.
    """
    new_email = serializers.EmailField(required=True, help_text=_("New email address"))
    old_email = serializers.EmailField(required=True, help_text=_("Old email address"))

    def validate(self, data):
        """
        Validate that the new email is not already in use and matches the old email.
        """
        new_email = data.get('new_email')
        old_email = data.get('old_email')

        if not constant_time_compare(str(new_email), str(old_email)):
            raise serializers.ValidationError("New email must be the same as old email for verification.")

        if User.objects.filter(email=new_email).exclude(pk=self.context['request'].user.pk).exists():
            raise serializers.ValidationError("Email is already in use by another account.")

        return data


class UpdateUserDetailsSerializer(serializers.ModelSerializer):
    """
    Serializer for updating user details including first name, last name, and profile information.
    """
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)

    class Meta:
        model = Profile
        fields = ['id', 'first_name', 'last_name', 'bio', 'profile_image', 'location', 'city']
        read_only_fields = ['id']

    def update(self, instance, validated_data):
        user_data = {}
        if 'user' in validated_data:
            user_data = validated_data.pop('user')

        if user_data:
            for attr, value in user_data.items():
                setattr(instance.user, attr, value)
            instance.user.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance
