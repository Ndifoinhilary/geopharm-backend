
from django import forms
from django.contrib.admin.widgets import AdminFileWidget
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm, UserChangeForm as BaseUserChangeForm
from django.core.exceptions import ValidationError
from django.utils.html import format_html

from .models import Profile

User = get_user_model()


class ImagePreviewWidget(AdminFileWidget):
    """Custom widget to preview images in admin"""

    def render(self, name, value, attrs=None, renderer=None):
        output = []
        if value and getattr(value, "url", None):
            image_url = value.url
            output.append(
                f'<div style="margin-bottom: 10px;">'
                f'<img src="{image_url}" width="150" height="150" '
                f'style="border-radius: 10px; object-fit: cover; border: 2px solid #ddd;" />'
                f'<br><small>Current image</small></div>'
            )
        output.append(super().render(name, value, attrs, renderer))
        return format_html(''.join(output))


class UserCreationForm(BaseUserCreationForm):
    """Custom user creation form for admin"""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'placeholder': 'user@example.com',
            'class': 'vTextField'
        }),
        help_text="Required. Enter a valid email address."
    )

    username = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'username',
            'class': 'vTextField'
        }),
        help_text="Required. 20 characters or fewer. Letters, digits and @/./+/-/_ only."
    )

    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'First name',
            'class': 'vTextField'
        })
    )

    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Last name',
            'class': 'vTextField'
        })
    )

    is_patient = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Designates whether the user is a patient."
    )

    is_pharmacy_owner = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Designates whether the user is a pharmacy owner."
    )

    send_verification_email = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Send verification email to the user after creation."
    )

    class Meta:
        model = User
        fields = (
            'email', 'username', 'first_name', 'last_name',
            'password1', 'password2', 'is_patient', 'is_pharmacy_owner'
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Reorder fields
        field_order = [
            'email', 'username', 'first_name', 'last_name',
            'password1', 'password2', 'is_patient', 'is_pharmacy_owner',
            'send_verification_email'
        ]
        self.fields = {key: self.fields[key] for key in field_order}

        # Add CSS classes and styling
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.TextInput) or isinstance(field.widget, forms.EmailInput):
                field.widget.attrs.update({'class': 'vTextField'})
            elif isinstance(field.widget, forms.PasswordInput):
                field.widget.attrs.update({'class': 'vPasswordField'})

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower().strip()
            if User.objects.filter(email=email).exists():
                raise ValidationError("A user with this email already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            username = username.lower().strip()
            if User.objects.filter(username=username).exists():
                raise ValidationError("A user with this username already exists.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        is_patient = cleaned_data.get('is_patient')
        is_pharmacy_owner = cleaned_data.get('is_pharmacy_owner')

        # Ensure a user has at least one role
        if not is_patient and not is_pharmacy_owner:
            cleaned_data['is_patient'] = True

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = user.email.lower()
        user.username = user.username.lower()

        if commit:
            user.save()

            if self.cleaned_data.get('send_verification_email'):
                pass

        return user


class UserChangeForm(BaseUserChangeForm):
    """Custom user change form for admin"""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'vTextField'})
    )

    username = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={'class': 'vTextField'})
    )

    class Meta:
        model = User
        fields = '__all__'
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'vTextField'}),
            'last_name': forms.TextInput(attrs={'class': 'vTextField'}),
            'otp_code': forms.TextInput(attrs={'class': 'vTextField', 'readonly': True}),
            'date_joined': forms.DateTimeInput(attrs={'class': 'vDateTimeField', 'readonly': True}),
            'last_login': forms.DateTimeInput(attrs={'class': 'vDateTimeField', 'readonly': True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


        if self.instance and self.instance.pk:

            self.fields['is_superuser'].help_text = (
                "Designates that this user has all permissions without explicitly assigning them. "
                "Use with caution!"
            )

            if self.instance.otp_code:
                from django.utils import timezone
                if self.instance.otp_expiry and self.instance.otp_expiry > timezone.now():
                    self.fields['otp_code'].help_text = f"Current OTP expires at {self.instance.otp_expiry}"
                else:
                    self.fields['otp_code'].help_text = "OTP has expired"
            else:
                self.fields['otp_code'].help_text = "No active OTP"

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower().strip()
            # Check for duplicates excluding current user
            if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
                raise ValidationError("A user with this email already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            username = username.lower().strip()
            # Check for duplicates excluding the current user
            if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
                raise ValidationError("A user with this username already exists.")
        return username


class ProfileAdminForm(forms.ModelForm):
    """Custom form for Profile admin"""

    class Meta:
        model = Profile
        fields = '__all__'
        widgets = {
            'bio': forms.Textarea(attrs={
                'rows': 4,
                'cols': 50,
                'class': 'vLargeTextField',
                'placeholder': 'Tell us about yourself...'
            }),
            'location': forms.TextInput(attrs={
                'class': 'vTextField',
                'placeholder': 'e.g., New York, USA'
            }),
            'city': forms.TextInput(attrs={
                'class': 'vTextField',
                'placeholder': 'e.g., New York'
            }),
            'profile_image': ImagePreviewWidget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'user' in self.fields:
            self.fields['user'].widget.attrs.update({'class': 'vForeignKeyRawIdAdminField'})


        self.fields[
            'bio'].help_text = "Optional. Tell users about yourself, your interests, or professional background."
        self.fields['location'].help_text = "Your general location (country, state, etc.)"
        self.fields['city'].help_text = "Your city of residence"

    def clean_profile_image(self):
        image = self.cleaned_data.get('profile_image')

        if image:

            if image.size > 5 * 1024 * 1024:
                raise ValidationError("Image file too large. Maximum size is 5MB.")


            from PIL import Image
            try:
                img = Image.open(image)
                width, height = img.size


                if width < 100 or height < 100:
                    raise ValidationError("Image is too small. Minimum size is 100x100 pixels.")


                if width > 2000 or height > 2000:
                    raise ValidationError("Image is too large. Maximum size is 2000x2000 pixels.")

            except Exception as e:
                raise ValidationError(f"Invalid image file: {str(e)}")

        return image


class BulkUserActionForm(forms.Form):
    """Form for bulk user actions"""

    ACTION_CHOICES = [
        ('activate', 'Activate Users'),
        ('deactivate', 'Deactivate Users'),
        ('verify', 'Verify Users'),
        ('send_verification', 'Send Verification Email'),
        ('unlock', 'Unlock Accounts'),
        ('reset_attempts', 'Reset Login Attempts'),
    ]

    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Select users to perform the action on"
    )

    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        help_text="Choose the action to perform"
    )

    confirmation = forms.BooleanField(
        required=True,
        help_text="I confirm that I want to perform this action on the selected users"
    )

    def __init__(self, *args, **kwargs):
        queryset = kwargs.pop('queryset', User.objects.all())
        super().__init__(*args, **kwargs)
        self.fields['users'].queryset = queryset


class UserFilterForm(forms.Form):
    """Advanced user filtering form"""

    USER_TYPE_CHOICES = [
        ('', 'All Users'),
        ('patient', 'Patients Only'),
        ('pharmacy_owner', 'Pharmacy Owners Only'),
        ('staff', 'Staff Only'),
        ('superuser', 'Superusers Only'),
    ]

    STATUS_CHOICES = [
        ('', 'All Statuses'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('verified', 'Verified'),
        ('unverified', 'Unverified'),
        ('locked', 'Locked'),
    ]

    user_type = forms.ChoiceField(
        choices=USER_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    date_joined_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    date_joined_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    last_login_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    last_login_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    search = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search by email, username, or name...',
            'class': 'form-control'
        })
    )


# Validation helper functions

def validate_user_permissions(user, requesting_user):
    """Validate that user can be modified by requesting user"""
    if not requesting_user.is_superuser:
        # Staff users can't modify superusers
        if user.is_superuser:
            raise ValidationError("You don't have permission to modify superuser accounts.")

        if user == requesting_user:
            raise ValidationError("You can't modify your own permissions.")

    return True


def get_user_stats():
    """Get user statistics for the dashboard"""
    from django.utils import timezone
    from datetime import timedelta

    stats = {
        'total_users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'verified_users': User.objects.filter(is_verified=True).count(),
        'locked_users': User.objects.filter(is_lock=True).count(),
        'patients': User.objects.filter(is_patient=True).count(),
        'pharmacy_owners': User.objects.filter(is_pharmacy_owner=True).count(),
        'staff_users': User.objects.filter(is_staff=True, is_superuser=False).count(),
        'superusers': User.objects.filter(is_superuser=True).count(),
        'recent_registrations': User.objects.filter(
            date_joined__gte=timezone.now() - timedelta(days=7)
        ).count(),
        'users_with_profiles': User.objects.filter(profile__isnull=False).count(),
    }

    # Calculate percentages
    total = stats['total_users']
    if total > 0:
        stats.update({
            'verification_rate': (stats['verified_users'] / total) * 100,
            'activity_rate': (stats['active_users'] / total) * 100,
            'profile_completion_rate': (stats['users_with_profiles'] / total) * 100,
        })
    else:
        stats.update({
            'verification_rate': 0,
            'activity_rate': 0,
            'profile_completion_rate': 0,
        })

    return stats
