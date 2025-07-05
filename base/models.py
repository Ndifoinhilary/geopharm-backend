import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.validators import FileExtensionValidator
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.translation import gettext_lazy as _

from pharm.models import BaseModel
from .manager import UserManager
from .utils import generate_otp_code, validate_profile_image


def profile_image_path(instance, filename):
    """Generate an upload path for profile images"""
    try:
        user_id = instance.user.id if instance.user else 'unknown'
        return f"profiles/{user_id}/{filename}"
    except AttributeError:
        return f"profiles/temp/{filename}"





class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model that extends AbstractBaseUser and PermissionsMixin.
    Uses email as the unique identifier instead of username.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the user")
    )

    email = models.EmailField(
        _("email address"),
        unique=True,
        error_messages={
            'unique': _("A user with that email already exists."),
        },
        help_text=_("Required. Enter a valid email address.")
    )

    username = models.CharField(
        _("username"),
        max_length=20,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^[\w.@+-]+$',
                message=_(
                    'Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters.')
            )
        ],
        help_text=_("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."),
        error_messages={
            'unique': _("A user with that username already exists."),
        }
    )

    first_name = models.CharField(
        _("first name"),
        max_length=150,
        blank=True,
        null=True,
        help_text=_("User's first name")
    )

    last_name = models.CharField(
        _("last name"),
        max_length=150,
        blank=True,
        null=True,
        help_text=_("User's last name")
    )

    otp_code = models.CharField(
        _("secure code"),
        max_length=6,
        null=True,
        blank=True,
        help_text=_("Auto-generated secure code for user verification")
    )

    otp_expiry = models.DateTimeField(
        verbose_name=_("secure code expiry"),
        help_text=_("The date and time when the secure code expires"),
        blank=True,
        null=True
    )

    is_active = models.BooleanField(
        _("active"),
        default=False,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    is_patient = models.BooleanField(
        default=True,
        verbose_name=_("is patient"),
        help_text=_("Designates whether the user is a patient.")
    )

    is_pharmacy_owner = models.BooleanField(
        default=False,
        verbose_name=_("is pharmacy owner"),
        help_text=_("Designates whether the user is a pharmacy owner.")
    )

    is_lock = models.BooleanField(
        default=False,
        verbose_name=_("is locked"),
        help_text=_("Designates whether the user account is locked due to too many failed login attempts.")
    )

    login_attempts = models.PositiveIntegerField(
        default=0,
        verbose_name=_("login attempts"),
        help_text=_("Number of failed login attempts")
    )

    locked_until = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("locked until"),
        help_text=_("The date and time until which the account is locked")
    )

    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )

    is_verified = models.BooleanField(
        _("verified"),
        default=False,
        help_text=_("Designates whether the user has verified their email address."),
    )

    date_joined = models.DateTimeField(
        _("date joined"),
        default=timezone.now,
        help_text=_("The date and time when the user account was created")
    )

    last_login = models.DateTimeField(
        _("last login"),
        blank=True,
        null=True,
        help_text=_("The date and time of the user's last login")
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['otp_code']),
            models.Index(fields=['is_active', 'is_staff']),
        ]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def save(self, *args, **kwargs):
        if not self.pk and not self.otp_code:
            self.otp_code = generate_otp_code()
            self.otp_expiry = timezone.now() + timedelta(minutes=10)

        self.email = self.__class__.objects.normalize_email(self.email)

        super().save(*args, **kwargs)

    @property
    def full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        """Return the user's first name."""
        return self.first_name

    def get_full_name(self):
        """Return the user's full name."""
        return self.full_name

    def activate(self):
        """Activate the user account."""
        self.is_active = True
        self.is_verified = True
        self.save(update_fields=['is_active', 'is_verified'])

    def deactivate(self):
        """Deactivate the user account."""
        self.is_active = False
        self.save(update_fields=['is_active'])

    def verify_user(self, otp_code=None):
        """Verify the user account."""
        if self.is_verified:
            raise ValueError(_("User is already verified."))
        if otp_code is None:
            raise ValueError(_("Secure code is required for verification."))
        if not constant_time_compare(str(self.otp_code), str(otp_code)):
            raise ValueError(_("Invalid secure code."))
        if self.otp_expiry < timezone.now():
            self.otp_code = None
            self.otp_expiry = None
            self.save(update_fields=['otp_code', 'otp_expiry'])
            raise ValueError(_("Secure code has expired."))

        self.is_verified = True
        self.is_active = True
        self.otp_code = None
        self.otp_expiry = None
        self.save(update_fields=['is_verified', 'is_active', 'otp_code', 'otp_expiry'])
        self.refresh_from_db()
        print(f"After save: otp_expiry = {self.otp_expiry}")

    def check_user_is_verified(self, otp_code=None) -> bool:
        """
        Check if the user is verified, attempting verification if needed.
        :param otp_code: The secure code for verification (required if not already verified)
        :return: True if the user is verified, False otherwise.
        """
        if self.is_verified:
            return True

        if otp_code is None:
            return False

        try:
            self.verify_user(otp_code)
            return True
        except ValueError:
            self.otp_code = generate_otp_code()
            self.otp_expiry = timezone.now() + timedelta(minutes=15)
            self.save(update_fields=['otp_code', 'otp_expiry'])
            return False

    def generate_new_otp_code(self):
        """Generate a new secure code for the user."""
        self.otp_code = generate_otp_code()
        self.otp_expiry = timezone.now() + timedelta(minutes=5)
        self.save(update_fields=['otp_code', 'otp_expiry'])
        return self.otp_code

    def is_locked(self):
        """
        Check if the user account is locked due to too many failed login attempts.
        :return: True if the account is locked, False otherwise.
        """
        if self.is_lock and self.locked_until:
            if timezone.now() < self.locked_until:
                return True
            else:
                # Lock period has expired, unlock the account
                self.unlock_account()
                return False
        return self.is_lock

    def lock_account(self):
        """Lock the user account for a specified duration."""
        self.is_lock = True
        self.locked_until = timezone.now() + settings.LOCK_UNTIL
        self.save(update_fields=['is_lock', 'locked_until'])

    def unlock_account(self):
        """Unlock the user account and reset login attempts."""
        self.is_lock = False
        self.locked_until = None
        self.login_attempts = 0
        self.save(update_fields=['is_lock', 'locked_until', 'login_attempts'])

    def increment_login_attempts(self):
        """Increment failed login attempts and lock if a threshold exceeded."""
        self.login_attempts += 1
        if self.login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            self.lock_account()
        else:
            self.save(update_fields=['login_attempts'])

    def reset_login_attempts(self):
        """Reset login attempts on successful login."""
        self.login_attempts = 0
        self.save(update_fields=['login_attempts'])


class Profile(BaseModel):
    """
    Profile model that extends the User model with additional fields.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='User',
        help_text="The user associated with this profile"
    )

    bio = models.TextField(
        null=True,
        blank=True,
        verbose_name='About yourself',
        help_text="A brief biography or description of the user"
    )

    profile_image = models.ImageField(
        _('profile image'),
        upload_to=profile_image_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'webp']
            ),
            validate_profile_image
        ],
        help_text=_('Upload a profile image (JPG, PNG, WebP). Max size: 5MB.')
    )

    location = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        verbose_name='Location',
        help_text="The location of the user, e.g., country or city"
    )

    city = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        verbose_name='City',
        help_text="The city where the user resides"
    )


    def __str__(self):
        return self.user.username

    def save(self, *args, **kwargs):
        if self.pk:
            try:
                old_profile = Profile.objects.get(pk=self.pk)
                if old_profile.profile_image != self.profile_image:
                    self.delete_old_images(old_profile)
            except Profile.DoesNotExist:
                pass

        super().save(*args, **kwargs)

    def delete_old_images(self, old_profile):
        """Delete old profile images."""
        if old_profile.profile_image:
            if default_storage.exists(old_profile.profile_image.name):
                default_storage.delete(old_profile.profile_image.name)

    def get_profile_image_url(self):
        """Get the profile image URL with fallback to default."""
        if self.profile_image:
            return self.profile_image.url
        return self.get_default_image_url()

    def get_default_image_url(self):
        """Return default profile image URL."""
        return f"{settings.STATIC_URL}images/default-profile.png"

    def delete_images(self):
        """Delete all associated images."""
        if self.profile_image:
            if default_storage.exists(self.profile_image.name):
                default_storage.delete(self.profile_image.name)

    def delete(self, *args, **kwargs):
        """Override delete to clean up image files."""
        self.delete_images()
        super().delete(*args, **kwargs)