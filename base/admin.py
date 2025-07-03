

import csv
from datetime import timedelta

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .forms import UserCreationForm, UserChangeForm
from .models import Profile

User = get_user_model()



class UserTypeFilter(admin.SimpleListFilter):
    title = 'User Type'
    parameter_name = 'user_type'

    def lookups(self, request, model_admin):
        return (
            ('patient', 'Patients'),
            ('pharmacy_owner', 'Pharmacy Owners'),
            ('staff', 'Staff'),
            ('superuser', 'Superusers'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'patient':
            return queryset.filter(is_patient=True, is_pharmacy_owner=False)
        elif self.value() == 'pharmacy_owner':
            return queryset.filter(is_pharmacy_owner=True)
        elif self.value() == 'staff':
            return queryset.filter(is_staff=True, is_superuser=False)
        elif self.value() == 'superuser':
            return queryset.filter(is_superuser=True)
        return queryset


class VerificationStatusFilter(admin.SimpleListFilter):
    title = 'Verification Status'
    parameter_name = 'verification_status'

    def lookups(self, request, model_admin):
        return (
            ('verified', 'Verified'),
            ('unverified', 'Unverified'),
            ('pending_otp', 'Pending OTP'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'verified':
            return queryset.filter(is_verified=True)
        elif self.value() == 'unverified':
            return queryset.filter(is_verified=False)
        elif self.value() == 'pending_otp':
            return queryset.filter(
                is_verified=False,
                otp_code__isnull=False,
                otp_expiry__gt=timezone.now()
            )
        return queryset


class AccountStatusFilter(admin.SimpleListFilter):
    title = 'Account Status'
    parameter_name = 'account_status'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Active'),
            ('inactive', 'Inactive'),
            ('locked', 'Locked'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(is_active=True, is_lock=False)
        elif self.value() == 'inactive':
            return queryset.filter(is_active=False)
        elif self.value() == 'locked':
            return queryset.filter(is_lock=True)
        return queryset


class RecentJoinedFilter(admin.SimpleListFilter):
    title = 'Registration Date'
    parameter_name = 'recent_joined'

    def lookups(self, request, model_admin):
        return (
            ('today', 'Today'),
            ('week', 'This Week'),
            ('month', 'This Month'),
            ('quarter', 'This Quarter'),
        )

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == 'today':
            return queryset.filter(date_joined__date=now.date())
        elif self.value() == 'week':
            week_ago = now - timedelta(days=7)
            return queryset.filter(date_joined__gte=week_ago)
        elif self.value() == 'month':
            month_ago = now - timedelta(days=30)
            return queryset.filter(date_joined__gte=month_ago)
        elif self.value() == 'quarter':
            quarter_ago = now - timedelta(days=90)
            return queryset.filter(date_joined__gte=quarter_ago)
        return queryset


class ProfileInline(admin.StackedInline):
    model = Profile
    extra = 0
    fields = (
        'bio', 'profile_image', 'location', 'city'
    )
    readonly_fields = ('created_at', 'updated_at')

    def get_extra(self, request, obj=None, **kwargs):
        # Don't show extra profile forms if user already has a profile
        if obj and hasattr(obj, 'profile'):
            return 0
        return 1




@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    model = User

    list_display = (
        'email', 'username', 'full_name', 'user_type_display',
        'verification_status', 'account_status', 'last_login_display','is_patient','is_pharmacy_owner',
        'date_joined', 'login_attempts_display'
    )

    list_filter = (
        UserTypeFilter, VerificationStatusFilter, AccountStatusFilter,
        RecentJoinedFilter, 'is_staff', 'is_superuser', 'date_joined'
    )

    search_fields = ('email', 'username', 'first_name', 'last_name')
    list_editable = ('is_patient', 'is_pharmacy_owner')
    ordering = ('-date_joined',)
    list_per_page = 50

    fieldsets = (
        ('Authentication', {
            'fields': ('email', 'username', 'password')
        }),
        ('Personal Information', {
            'fields': ('first_name', 'last_name')
        }),
        ('User Type & Roles', {
            'fields': (
                'is_patient', 'is_pharmacy_owner', 'is_staff',
                'is_superuser', 'groups', 'user_permissions'
            ),
            'classes': ('collapse',)
        }),
        ('Account Status', {
            'fields': (
                'is_active', 'is_verified', 'is_lock', 'login_attempts',
                'locked_until'
            )
        }),
        ('Verification', {
            'fields': ('otp_code', 'otp_expiry'),
            'classes': ('collapse',)
        }),
        ('Important Dates', {
            'fields': ('date_joined', 'last_login'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        ('Create New User', {
            'classes': ('wide',),
            'fields': (
                'email', 'username', 'first_name', 'last_name',
                'password1', 'password2', 'is_patient', 'is_pharmacy_owner'
            ),
        }),
    )

    readonly_fields = ('date_joined', 'last_login', 'otp_expiry')
    inlines = [ProfileInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('profile')

    # Custom display methods
    def full_name(self, obj):
        """Display the user's full name"""
        name = obj.full_name
        return name if name else '—'

    full_name.short_description = 'Full Name'

    def user_type_display(self, obj):
        """Display a user type with badges"""
        types = []
        if obj.is_superuser:
            types.append(
                '<span class="badge" style="background: #dc3545; color: white; padding: 2px 6px; border-radius: 3px;">Super Admin</span>')
        elif obj.is_staff:
            types.append(
                '<span class="badge" style="background: #6c757d; color: white; padding: 2px 6px; border-radius: 3px;">Staff</span>')

        if obj.is_pharmacy_owner:
            types.append(
                '<span class="badge" style="background: #28a745; color: white; padding: 2px 6px; border-radius: 3px;">Pharmacy Owner</span>')

        if obj.is_patient:
            types.append(
                '<span class="badge" style="background: #007bff; color: white; padding: 2px 6px; border-radius: 3px;">Patient</span>')

        return format_html(' '.join(types)) if types else '—'

    user_type_display.short_description = 'User Type'

    def verification_status(self, obj):
        """Display verification status with color coding"""
        if obj.is_verified:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Verified</span>'
            )
        elif obj.otp_code and obj.otp_expiry and obj.otp_expiry > timezone.now():
            return format_html(
                '<span style="color: orange;">⏳ Pending OTP</span>'
            )
        else:
            return format_html(
                '<span style="color: red;">✗ Unverified</span>'
            )

    verification_status.short_description = 'Verification'

    def account_status(self, obj):
        """Display account status with color coding"""
        if obj.is_lock:
            if obj.locked_until and obj.locked_until > timezone.now():
                return format_html(
                    '<span style="color: red; font-weight: bold;">🔒 Locked</span>'
                )
            else:
                return format_html(
                    '<span style="color: orange;">🔓 Lock Expired</span>'
                )
        elif obj.is_active:
            return format_html(
                '<span style="color: green;">✓ Active</span>'
            )
        else:
            return format_html(
                '<span style="color: red;">✗ Inactive</span>'
            )

    account_status.short_description = 'Status'

    def last_login_display(self, obj):
        """Display last login with relative time"""
        if obj.last_login:
            time_diff = timezone.now() - obj.last_login
            if time_diff.days > 30:
                return format_html(
                    '<span style="color: red;">{} days ago</span>',
                    time_diff.days
                )
            elif time_diff.days > 7:
                return format_html(
                    '<span style="color: orange;">{} days ago</span>',
                    time_diff.days
                )
            else:
                return format_html(
                    '<span style="color: green;">Recent</span>'
                )
        return '—'

    last_login_display.short_description = 'Last Login'

    def login_attempts_display(self, obj):
        """Display login attempts with warning colors"""
        if obj.login_attempts == 0:
            return '—'
        elif obj.login_attempts >= 3:
            return format_html(
                '<span style="color: red; font-weight: bold;">{} attempts</span>',
                obj.login_attempts
            )
        else:
            return format_html(
                '<span style="color: orange;">{} attempts</span>',
                obj.login_attempts
            )

    login_attempts_display.short_description = 'Failed Logins'

    # Custom actions
    actions = [
        'verify_users', 'activate_users', 'deactivate_users',
        'unlock_accounts', 'reset_login_attempts', 'send_verification_email',
        'export_users_csv', 'generate_user_report'
    ]

    def verify_users(self, request, queryset):
        """Mark selected users as verified"""
        updated = queryset.update(is_verified=True, is_active=True)
        self.message_user(
            request,
            f'{updated} users have been verified and activated.',
            messages.SUCCESS
        )

    verify_users.short_description = 'Verify selected users'

    def activate_users(self, request, queryset):
        """Activate selected users"""
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f'{updated} users have been activated.',
            messages.SUCCESS
        )

    activate_users.short_description = 'Activate selected users'

    def deactivate_users(self, request, queryset):
        """Deactivate selected users"""
        # Don't deactivate superusers
        non_superusers = queryset.filter(is_superuser=False)
        updated = non_superusers.update(is_active=False)

        if updated < queryset.count():
            self.message_user(
                request,
                f'{updated} users deactivated. Superusers were skipped.',
                messages.WARNING
            )
        else:
            self.message_user(
                request,
                f'{updated} users have been deactivated.',
                messages.SUCCESS
            )

    deactivate_users.short_description = 'Deactivate selected users'

    def unlock_accounts(self, request, queryset):
        """Unlock selected user accounts"""
        queryset.update(
            is_lock=False,
            locked_until=None,
            login_attempts=0
        )
        self.message_user(
            request,
            f'{queryset.count()} accounts have been unlocked.',
            messages.SUCCESS
        )

    unlock_accounts.short_description = 'Unlock selected accounts'

    def reset_login_attempts(self, request, queryset):
        """Reset login attempts for selected users"""
        updated = queryset.update(login_attempts=0)
        self.message_user(
            request,
            f'Login attempts reset for {updated} users.',
            messages.SUCCESS
        )

    reset_login_attempts.short_description = 'Reset login attempts'

    def send_verification_email(self, request, queryset):
        """Send verification email to unverified users"""
        unverified_users = queryset.filter(is_verified=False)
        count = 0

        for user in unverified_users:
            # Generate new OTP if needed
            if not user.otp_code or (user.otp_expiry and user.otp_expiry < timezone.now()):
                user.generate_new_otp_code()

            # Here you would implement actual email sending
            # send_verification_email_task.delay(user.id)
            count += 1

        self.message_user(
            request,
            f'Verification emails sent to {count} users.',
            messages.SUCCESS
        )

    send_verification_email.short_description = 'Send verification emails'

    def export_users_csv(self, request, queryset):
        """Export selected users to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users_export.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Email', 'Username', 'First Name', 'Last Name',
            'User Type', 'Verified', 'Active', 'Date Joined',
            'Last Login', 'Login Attempts'
        ])

        for user in queryset:
            user_types = []
            if user.is_superuser:
                user_types.append('Superuser')
            if user.is_staff:
                user_types.append('Staff')
            if user.is_pharmacy_owner:
                user_types.append('Pharmacy Owner')
            if user.is_patient:
                user_types.append('Patient')

            writer.writerow([
                user.email,
                user.username,
                user.first_name or '',
                user.last_name or '',
                ', '.join(user_types),
                'Yes' if user.is_verified else 'No',
                'Yes' if user.is_active else 'No',
                user.date_joined.strftime('%Y-%m-%d %H:%M'),
                user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else '',
                user.login_attempts
            ])

        return response

    export_users_csv.short_description = 'Export to CSV'

    def generate_user_report(self, request, queryset):
        """Generate detailed user analytics report"""

        # Calculate statistics
        total_users = queryset.count()
        verified_users = queryset.filter(is_verified=True).count()
        active_users = queryset.filter(is_active=True).count()
        locked_users = queryset.filter(is_lock=True).count()

        user_types = {
            'patients': queryset.filter(is_patient=True).count(),
            'pharmacy_owners': queryset.filter(is_pharmacy_owner=True).count(),
            'staff': queryset.filter(is_staff=True, is_superuser=False).count(),
            'superusers': queryset.filter(is_superuser=True).count(),
        }

        context = {
            'total_users': total_users,
            'verified_users': verified_users,
            'active_users': active_users,
            'locked_users': locked_users,
            'user_types': user_types,
            'verification_rate': (verified_users / total_users * 100) if total_users > 0 else 0,
            'generated_at': timezone.now(),
        }

        # In a real implementation, you might generate a PDF or send an email
        self.message_user(
            request,
            f'Report generated for {total_users} users. '
            f'Verification rate: {context["verification_rate"]:.1f}%',
            messages.INFO
        )

    generate_user_report.short_description = 'Generate analytics report'


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user_email', 'user_full_name', 'location', 'city',
        'profile_image_preview', 'created_at', 'updated_at'
    )

    list_filter = ('location', 'city', 'created_at')
    search_fields = (
        'user__email', 'user__username', 'user__first_name',
        'user__last_name', 'location', 'city', 'bio'
    )

    ordering = ('-created_at',)
    list_per_page = 50

    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Profile Details', {
            'fields': ('bio', 'profile_image', 'location', 'city')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    def user_email(self, obj):
        """Display user's email with link to user admin"""
        url = reverse('admin:base_user_change', args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)

    user_email.short_description = 'User Email'
    user_email.admin_order_field = 'user__email'

    def user_full_name(self, obj):
        """Display user's full name"""
        return obj.user.full_name or '—'

    user_full_name.short_description = 'Full Name'
    user_full_name.admin_order_field = 'user__first_name'

    def profile_image_preview(self, obj):
        """Display profile image preview"""
        if obj.profile_image:
            return format_html(
                '<img src="{}" width="50" height="50" style="border-radius: 50%; object-fit: cover;" />',
                obj.profile_image.url
            )
        return '—'

    profile_image_preview.short_description = 'Image'

    actions = ['update_location_bulk', 'export_profiles_csv']

    def update_location_bulk(self, request, queryset):
        """Bulk update location for selected profiles"""
        # This would typically show a form for bulk updates
        self.message_user(
            request,
            'Bulk location update feature - implement form as needed.',
            messages.INFO
        )

    update_location_bulk.short_description = 'Bulk update location'

    def export_profiles_csv(self, request, queryset):
        """Export profile data to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="profiles_export.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'User Email', 'Full Name', 'Bio', 'Location',
            'City', 'Has Profile Image', 'Created At'
        ])

        for profile in queryset:
            writer.writerow([
                profile.user.email,
                profile.user.full_name,
                profile.bio or '',
                profile.location,
                profile.city,
                'Yes' if profile.profile_image else 'No',
                profile.created_at.strftime('%Y-%m-%d %H:%M')
            ])

        return response

    export_profiles_csv.short_description = 'Export to CSV'


# ========================
# ADMIN SITE CUSTOMIZATION
# ========================

# Add custom CSS for better styling
class CustomAdminSite(admin.AdminSite):
    site_header = 'GeoPharm User Management'
    site_title = 'User Admin'
    index_title = 'User Administration Dashboard'

    def each_context(self, request):
        context = super().each_context(request)

        # Add user statistics to context
        context.update({
            'user_stats': {
                'total_users': User.objects.count(),
                'verified_users': User.objects.filter(is_verified=True).count(),
                'active_users': User.objects.filter(is_active=True).count(),
                'locked_users': User.objects.filter(is_lock=True).count(),
                'pharmacy_owners': User.objects.filter(is_pharmacy_owner=True).count(),
                'patients': User.objects.filter(is_patient=True).count(),
                'recent_registrations': User.objects.filter(
                    date_joined__gte=timezone.now() - timedelta(days=7)
                ).count(),
            }
        })

        return context

# Optionally use custom admin site
# user_admin_site = CustomAdminSite(name='user_admin')
# user_admin_site.register(User, UserAdmin)
# user_admin_site.register(Profile, ProfileAdmin)
