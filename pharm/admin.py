
import csv
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Count, Avg
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    DrugCategory, Drug, Pharmacy, PharmacyRating, SavedPharmacy,
    PharmacyVisit, Inventory, InventoryAlert, PriceHistory, SearchHistory
)

User = get_user_model()




class ApplicationStatusFilter(admin.SimpleListFilter):
    title = 'Application Status'
    parameter_name = 'application_status'

    def lookups(self, request, model_admin):
        return (
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(application_status=self.value())
        return queryset


class StockStatusFilter(admin.SimpleListFilter):
    title = 'Stock Status'
    parameter_name = 'stock_status'

    def lookups(self, request, model_admin):
        return (
            ('available', 'Available'),
            ('low_stock', 'Low Stock'),
            ('out_of_stock', 'Out of Stock'),
            ('discontinued', 'Discontinued'),
        )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class ExpiryStatusFilter(admin.SimpleListFilter):
    title = 'Expiry Status'
    parameter_name = 'expiry_status'

    def lookups(self, request, model_admin):
        return (
            ('expired', 'Expired'),
            ('expiring_soon', 'Expiring Soon (30 days)'),
            ('fresh', 'Fresh (>30 days)'),
        )

    def queryset(self, request, queryset):
        if self.value():
            today = timezone.now().date()
            if self.value() == 'expired':
                return queryset.filter(expiry_date__lt=today)
            elif self.value() == 'expiring_soon':
                return queryset.filter(
                    expiry_date__gte=today,
                    expiry_date__lte=today + timedelta(days=30)
                )
            elif self.value() == 'fresh':
                return queryset.filter(expiry_date__gt=today + timedelta(days=30))
        return queryset




class InventoryInline(admin.TabularInline):
    model = Inventory
    extra = 0
    fields = ('drug', 'quantity', 'price', 'status', 'expiry_date')
    readonly_fields = ('status',)
    show_change_link = True


class PharmacyRatingInline(admin.TabularInline):
    model = PharmacyRating
    extra = 0
    fields = ('user', 'rating', 'review', 'created_at')
    readonly_fields = ('created_at',)


class PriceHistoryInline(admin.TabularInline):
    model = PriceHistory
    extra = 0
    fields = ('old_price', 'new_price', 'changed_by', 'reason', 'changed_at')
    readonly_fields = ('changed_at',)


class InventoryAlertInline(admin.TabularInline):
    model = InventoryAlert
    extra = 0
    fields = ('alert_type', 'message', 'is_resolved', 'created_at')
    readonly_fields = ('created_at',)




@admin.register(DrugCategory)
class DrugCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'drug_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'description')
    ordering = ('name',)

    def drug_count(self, obj):
        """Display number of drugs in this category"""
        count = obj.drugs.count()
        if count:
            url = reverse('admin:pharm_drug_changelist') + f'?category__id__exact={obj.id}'
            return format_html('<a href="{}">{} drugs</a>', url, count)
        return '0 drugs'

    drug_count.short_description = 'Number of Drugs'

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            drug_count=Count('drugs')
        )


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'category', 'dosage', 'drug_form', 'manufacturer',
        'requires_prescription', 'inventory_count', 'image_preview'
    )
    list_filter = (
        'category', 'requires_prescription', 'drug_form',
        'manufacturer', 'created_at'
    )
    search_fields = ('name', 'generic_name', 'manufacturer')
    list_editable = ('requires_prescription',)
    ordering = ('name',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category', 'generic_name', 'manufacturer')
        }),
        ('Drug Details', {
            'fields': ('dosage', 'drug_form', 'description', 'side_effects')
        }),
        ('Requirements & Image', {
            'fields': ('requires_prescription', 'image')
        }),
    )

    def inventory_count(self, obj):
        """Display the number of pharmacies that stock this drug"""
        count = obj.inventory.count()
        if count:
            url = reverse('admin:pharm_inventory_changelist') + f'?drug__id__exact={obj.id}'
            return format_html('<a href="{}">{} pharmacies</a>', url, count)
        return '0 pharmacies'

    inventory_count.short_description = 'Available At'

    def image_preview(self, obj):
        """Display small preview of drug image"""
        if obj.image:
            return format_html(
                '<img src="{}" width="50" height="50" style="border-radius: 5px;" />',
                obj.image.url
            )
        return '—'

    image_preview.short_description = 'Image'

    actions = ['mark_as_prescription_required', 'mark_as_no_prescription']

    def mark_as_prescription_required(self, request, queryset):
        queryset.update(requires_prescription=True)
        self.message_user(request, f'{queryset.count()} drugs marked as prescription required.')

    mark_as_prescription_required.short_description = 'Mark as prescription required'

    def mark_as_no_prescription(self, request, queryset):
        queryset.update(requires_prescription=False)
        self.message_user(request, f'{queryset.count()} drugs marked as no prescription required.')

    mark_as_no_prescription.short_description = 'Mark as no prescription required'


@admin.register(Pharmacy)
class PharmacyAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'owner', 'city', 'application_status', 'verified',
        'is_24_hours', 'total_inventory', 'average_rating', 'created_at'
    )
    list_filter = (
        ApplicationStatusFilter, 'verified', 'is_24_hours',
        'city', 'created_at'
    )
    search_fields = ('name', 'owner__email', 'city', 'address', 'license_number')
    list_editable = ('application_status', 'verified')
    ordering = ('-created_at',)

    fieldsets = (
        ('Owner Information', {
            'fields': ('owner',)
        }),
        ('Pharmacy Details', {
            'fields': ('name', 'description', 'license_number', 'established_date')
        }),
        ('Location & Contact', {
            'fields': ('address', 'city', 'latitude', 'longitude', 'phone', 'email', 'website')
        }),
        ('Operating Hours', {
            'fields': ('opening_hours', 'working_hours', 'is_24_hours')
        }),
        ('Application Status', {
            'fields': ('application_status', 'verified', 'rejection_reason'),
            'classes': ('collapse',)
        }),
        ('Media Files', {
            'fields': ('profile_image', 'logo', 'certificate_of_operation'),
            'classes': ('collapse',)
        }),
    )

    inlines = [InventoryInline, PharmacyRatingInline]

    def total_inventory(self, obj):
        """Display total number of drugs in inventory"""
        return obj.total_drugs

    total_inventory.short_description = 'Total Drugs'

    def average_rating(self, obj):
        """Display average rating with stars"""
        avg_rating = obj.ratings.aggregate(avg=Avg('rating'))['avg']
        if avg_rating:
            stars = '★' * int(avg_rating) + '☆' * (5 - int(avg_rating))
            return format_html('{} ({})', stars, avg_rating)
        return '—'

    average_rating.short_description = 'Rating'

    actions = ['approve_pharmacies', 'reject_pharmacies', 'mark_as_verified', 'export_to_csv']

    def approve_pharmacies(self, request, queryset):
        queryset.update(application_status='approved', verified=True)
        self.message_user(request, f'{queryset.count()} pharmacies approved.')

    approve_pharmacies.short_description = 'Approve selected pharmacies'

    def reject_pharmacies(self, request, queryset):
        queryset.update(application_status='rejected', verified=False)
        self.message_user(request, f'{queryset.count()} pharmacies rejected.')

    reject_pharmacies.short_description = 'Reject selected pharmacies'

    def mark_as_verified(self, request, queryset):
        queryset.update(verified=True)
        self.message_user(request, f'{queryset.count()} pharmacies marked as verified.')

    mark_as_verified.short_description = 'Mark as verified'

    def export_to_csv(self, request, queryset):
        """Export selected pharmacies to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="pharmacies.csv"'

        writer = csv.writer(response)
        writer.writerow(['Name', 'Owner', 'City', 'Status', 'Verified', 'Phone', 'Email'])

        for pharmacy in queryset:
            writer.writerow([
                pharmacy.name,
                pharmacy.owner.email,
                pharmacy.city,
                pharmacy.application_status,
                pharmacy.verified,
                pharmacy.phone,
                pharmacy.email
            ])

        return response

    export_to_csv.short_description = 'Export to CSV'


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        'pharmacy', 'drug', 'quantity', 'price', 'cost_price',
        'status', 'profit_margin_display', 'expiry_status', 'last_updated'
    )
    list_filter = (
        StockStatusFilter, ExpiryStatusFilter, 'pharmacy',
        'drug__category', 'last_updated'
    )
    search_fields = (
        'pharmacy__name', 'drug__name', 'drug__generic_name',
        'batch_number', 'supplier'
    )
    list_editable = ('quantity', 'price')
    ordering = ('-last_updated',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('pharmacy', 'drug', 'quantity', 'status')
        }),
        ('Pricing', {
            'fields': ('price', 'cost_price', 'low_stock_threshold')
        }),
        ('Product Details', {
            'fields': ('expiry_date', 'batch_number', 'supplier', 'notes')
        }),
    )

    readonly_fields = ('status',)
    inlines = [PriceHistoryInline, InventoryAlertInline]

    def profit_margin_display(self, obj):
        """Display profit margin with color coding"""
        margin = obj.profit_margin
        if margin is not None:
            if margin > 50:
                color = 'green'
            elif margin > 20:
                color = 'orange'
            else:
                color = 'red'
            return format_html(
                '<span style="color: {};">{}%</span>',
                color, margin
            )
        return '—'

    profit_margin_display.short_description = 'Profit Margin'

    def expiry_status(self, obj):
        """Display expiry status with color coding"""
        if obj.expiry_date:
            days = obj.days_until_expiry
            if days < 0:
                return format_html('<span style="color: red;">Expired</span>')
            elif days <= 30:
                return format_html('<span style="color: orange;">Expiring Soon</span>')
            else:
                return format_html('<span style="color: green;">Fresh</span>')
        return '—'

    expiry_status.short_description = 'Expiry Status'

    actions = ['mark_as_discontinued', 'generate_alerts', 'export_low_stock']

    def mark_as_discontinued(self, request, queryset):
        queryset.update(status='discontinued')
        self.message_user(request, f'{queryset.count()} items marked as discontinued.')

    mark_as_discontinued.short_description = 'Mark as discontinued'

    def generate_alerts(self, request, queryset):
        """Generate alerts for low stock and expiring items"""
        alerts_created = 0
        for item in queryset:
            if item.status == 'low_stock':
                InventoryAlert.objects.get_or_create(
                    inventory=item,
                    alert_type='low_stock',
                    defaults={'message': f'Low stock alert for {item.drug.name}'}
                )
                alerts_created += 1
            elif item.is_expired:
                InventoryAlert.objects.get_or_create(
                    inventory=item,
                    alert_type='expired',
                    defaults={'message': f'Expired: {item.drug.name}'}
                )
                alerts_created += 1

        self.message_user(request, f'{alerts_created} alerts generated.')

    generate_alerts.short_description = 'Generate alerts for selected items'

    def export_low_stock(self, request, queryset):
        """Export low stock items to CSV"""
        low_stock_items = queryset.filter(status__in=['low_stock', 'out_of_stock'])

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="low_stock_items.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Pharmacy', 'Drug', 'Current Stock', 'Threshold',
            'Status', 'Supplier', 'Last Updated'
        ])

        for item in low_stock_items:
            writer.writerow([
                item.pharmacy.name,
                item.drug.name,
                item.quantity,
                item.low_stock_threshold,
                item.status,
                item.supplier,
                item.last_updated.strftime('%Y-%m-%d')
            ])

        return response

    export_low_stock.short_description = 'Export low stock items to CSV'


@admin.register(PharmacyRating)
class PharmacyRatingAdmin(admin.ModelAdmin):
    list_display = ('pharmacy', 'user', 'rating', 'review_preview', 'created_at')
    list_filter = ('rating', 'created_at', 'pharmacy')
    search_fields = ('pharmacy__name', 'user__email', 'review')
    ordering = ('-created_at',)

    def review_preview(self, obj):
        """Display truncated review"""
        if obj.review:
            return obj.review[:50] + '...' if len(obj.review) > 50 else obj.review
        return '—'

    review_preview.short_description = 'Review'

    actions = ['moderate_reviews']

    def moderate_reviews(self, request, queryset):
        """Mark reviews as moderated"""
        # You can add a moderated field to the model if needed
        self.message_user(request, f'{queryset.count()} reviews moderated.')

    moderate_reviews.short_description = 'Moderate selected reviews'


@admin.register(SavedPharmacy)
class SavedPharmacyAdmin(admin.ModelAdmin):
    list_display = ('user', 'pharmacy', 'saved_at')
    list_filter = ('saved_at', 'pharmacy')
    search_fields = ('user__email', 'pharmacy__name')
    ordering = ('-saved_at',)


@admin.register(PharmacyVisit)
class PharmacyVisitAdmin(admin.ModelAdmin):
    list_display = ('user', 'pharmacy', 'visited_at')
    list_filter = ('visited_at', 'pharmacy')
    search_fields = ('user__email', 'pharmacy__name')
    ordering = ('-visited_at',)

    actions = ['export_visit_analytics']

    def export_visit_analytics(self, request, queryset):
        """Export visit analytics to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="visit_analytics.csv"'

        writer = csv.writer(response)
        writer.writerow(['User', 'Pharmacy', 'Visit Date', 'Day of Week'])

        for visit in queryset:
            writer.writerow([
                visit.user.email,
                visit.pharmacy.name,
                visit.visited_at.strftime('%Y-%m-%d %H:%M'),
                visit.visited_at.strftime('%A')
            ])

        return response

    export_visit_analytics.short_description = 'Export visit analytics'


@admin.register(InventoryAlert)
class InventoryAlertAdmin(admin.ModelAdmin):
    list_display = (
        'inventory', 'alert_type', 'message_preview',
        'is_resolved', 'created_at'
    )
    list_filter = ('alert_type', 'is_resolved', 'created_at')
    search_fields = ('inventory__pharmacy__name', 'inventory__drug__name', 'message')
    list_editable = ('is_resolved',)
    ordering = ('-created_at',)

    def message_preview(self, obj):
        """Display a truncated message"""
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message

    message_preview.short_description = 'Message'

    actions = ['mark_as_resolved', 'mark_as_unresolved']

    def mark_as_resolved(self, request, queryset):
        queryset.update(is_resolved=True)
        self.message_user(request, f'{queryset.count()} alerts marked as resolved.')

    mark_as_resolved.short_description = 'Mark as resolved'

    def mark_as_unresolved(self, request, queryset):
        queryset.update(is_resolved=False)
        self.message_user(request, f'{queryset.count()} alerts marked as unresolved.')

    mark_as_unresolved.short_description = 'Mark as unresolved'


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'inventory', 'old_price', 'new_price', 'price_change',
        'changed_by', 'reason', 'changed_at'
    )
    list_filter = ('changed_at', 'changed_by')
    search_fields = (
        'inventory__pharmacy__name', 'inventory__drug__name',
        'reason', 'changed_by__email'
    )
    ordering = ('-changed_at',)

    def price_change(self, obj):
        """Display price change with color coding"""
        change = obj.new_price - obj.old_price
        if change > 0:
            return format_html(
                '<span style="color: red;">+${}</span>',
                change
            )
        elif change < 0:
            return format_html(
                '<span style="color: green;">${}</span>',
                change
            )
        else:
            return '$0.00'

    price_change.short_description = 'Price Change'

    actions = ['export_price_trends']

    def export_price_trends(self, request, queryset):
        """Export price trends to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="price_trends.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Pharmacy', 'Drug', 'Old Price', 'New Price',
            'Change', 'Date', 'Changed By', 'Reason'
        ])

        for history in queryset:
            change = history.new_price - history.old_price
            writer.writerow([
                history.inventory.pharmacy.name,
                history.inventory.drug.name,
                history.old_price,
                history.new_price,
                change,
                history.changed_at.strftime('%Y-%m-%d'),
                history.changed_by.email if history.changed_by else 'System',
                history.reason
            ])

        return response

    export_price_trends.short_description = 'Export price trends'


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'query', 'searched_at')
    list_filter = ('searched_at',)
    search_fields = ('user__email', 'query')
    ordering = ('-searched_at',)

    actions = ['export_search_analytics']

    def export_search_analytics(self, request, queryset):
        """Export search analytics to CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="search_analytics.csv"'

        writer = csv.writer(response)
        writer.writerow(['User', 'Search Query', 'Search Date'])

        for search in queryset:
            writer.writerow([
                search.user.email,
                search.query,
                search.searched_at.strftime('%Y-%m-%d %H:%M')
            ])

        return response

    export_search_analytics.short_description = 'Export search analytics'





class CustomAdminSite(admin.AdminSite):
    site_header = 'GeoPharm Administration'
    site_title = 'GeoPharm Admin'
    index_title = 'Administration Dashboard'

    def index(self, request, extra_context=None):
        """Custom admin dashboard with statistics"""
        extra_context = extra_context or {}

        # Add dashboard statistics
        extra_context.update({
            'total_pharmacies': Pharmacy.objects.count(),
            'pending_applications': Pharmacy.objects.filter(application_status='pending').count(),
            'total_drugs': Drug.objects.count(),
            'low_stock_alerts': InventoryAlert.objects.filter(
                alert_type__in=['low_stock', 'out_of_stock'],
                is_resolved=False
            ).count(),
            'total_users': User.objects.count(),
        })

        return super().index(request, extra_context)

# Uncomment to use custom admin site
# admin_site = CustomAdminSite(name='custom_admin')
# Register all models with a custom admin site if using
