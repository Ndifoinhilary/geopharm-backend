import math
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

from base.utils import validate_certificate_size_format

User = settings.AUTH_USER_MODEL


def upload_image_path(instance, filename):
    """
    Custom upload_to function for file fields.
    Generates a unique filename based on the model name and current timestamp.
    """
    import time
    return f"{instance.__class__.__name__.lower()}/{int(time.time())}_{filename}"


class BaseModel(models.Model):
    """
    Base model to include common fields for all models.
    """
    id = models.UUIDField(
        primary_key=True,
        editable=False,
        default=uuid.uuid4,
        verbose_name=_("ID"),
        help_text=_("Unique identifier for the model")
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
        help_text=_("Timestamp when the model was created")
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At"),
        help_text=_("Timestamp when the model was last updated")
    )

    class Meta:
        abstract = True


class DrugCategory(BaseModel):
    """
    DrugCategory model represents a category of drugs.
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("Name"),
        help_text=_("Name of the drug category")
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Description of the drug category")
    )

    class Meta:
        verbose_name_plural = "Drug Categories"
        ordering = ['name']
        indexes = [
            models.Index(fields=['name'], name='drug_category_name_idx'),
        ]

    def __str__(self):
        return self.name


class Drug(BaseModel):
    """
    Drug model represents a pharmaceutical drug with its details.
    """
    name = models.CharField(
        max_length=200,
        verbose_name=_("Name"),
        help_text=_("Name of the drug")
    )

    category = models.ForeignKey(
        DrugCategory,
        on_delete=models.CASCADE,
        related_name='drugs',
        verbose_name=_("Category"),
        help_text=_("Category of the drug")
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Description of the drug")
    )

    generic_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Generic Name"),
        help_text=_("Generic name of the drug")
    )

    manufacturer = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Manufacturer"),
        help_text=_("Manufacturer of the drug")
    )

    dosage = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Dosage"),
        help_text=_("Dosage of the drug, e.g., '500mg'")
    )

    drug_form = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Drug Form"),
        help_text=_("Form of the drug, e.g., 'Tablet', 'Syrup'")
    )

    side_effects = models.TextField(
        blank=True,
        verbose_name=_("Side Effects"),
        help_text=_("Common side effects of the drug")
    )

    requires_prescription = models.BooleanField(
        default=False,
        verbose_name=_("Requires Prescription"),
        help_text=_("Indicates if the drug requires a prescription")
    )

    image = models.ImageField(
        upload_to=upload_image_path,
        blank=True,
        verbose_name=_("Image"),
        help_text=_("The image of the drug")
    )

    class Meta:
        unique_together = ['name', 'dosage']
        ordering = ['name']
        verbose_name_plural = "Drugs"

    def __str__(self):
        return f"{self.name} - {self.dosage}" if self.dosage else self.name


class Pharmacy(BaseModel):
    """
    Pharmacy model represents a pharmacy with its details and location.
    """
    owner = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='pharmacy',
        verbose_name=_("Owner"),
        help_text=_("Owner of the pharmacy")
    )

    name = models.CharField(
        max_length=200,
        verbose_name=_("Name"),
        help_text=_("Name of the pharmacy")
    )

    address = models.TextField(
        verbose_name=_("Address"),
        help_text=_("Address of the pharmacy")
    )

    city = models.CharField(
        max_length=100,
        verbose_name=_("City"),
        help_text=_("City where the pharmacy is located")
    )

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=8,
        null=True,
        blank=True,
        verbose_name=_("Latitude"),
        help_text=_("Latitude of the pharmacy location")
    )

    longitude = models.DecimalField(
        max_digits=11,
        decimal_places=8,
        null=True,
        blank=True,
        verbose_name=_("Longitude"),
        help_text=_("Longitude of the pharmacy location")
    )

    phone = PhoneNumberField(
        max_length=20,
        blank=True,
        verbose_name=_("Phone"),
        help_text=_("Phone number of the pharmacy")
    )

    email = models.EmailField(
        blank=True,
        verbose_name=_("Email"),
        help_text=_("Email address of the pharmacy")
    )

    website = models.URLField(
        blank=True,
        null=True,
        verbose_name=_("Website"),
        help_text=_("Website URL of the pharmacy")
    )

    opening_hours = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("Opening Hours"),
        help_text=_("Opening hours of the pharmacy, e.g., '9 AM - 9 PM'")
    )

    verified = models.BooleanField(
        default=False,
        verbose_name=_("Verified"),
        help_text=_("Indicates if the pharmacy is verified")
    )

    working_hours = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("Working Hours"),
        help_text=_("Working hours of the pharmacy, e.g., '9 AM - 5 PM'")
    )

    is_24_hours = models.BooleanField(
        default=False,
        verbose_name=_("24 Hours"),
        help_text=_("Indicates if the pharmacy operates 24 hours")
    )

    license_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("License Number"),
        help_text=_("License number of the pharmacy"))

    established_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Established Date"),
        help_text=_("Date when the pharmacy was established")
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Description of the pharmacy")
    )

    profile_image = models.ImageField(
        upload_to=upload_image_path,
        blank=True,
        verbose_name=_("Profile Image"),
        help_text=_("Profile image of the pharmacy")
    )

    logo = models.ImageField(
        upload_to=upload_image_path,
        blank=True,
        verbose_name=_("Logo"),
        help_text=_("Logo of the pharmacy")
    )
    rejection_reason = models.TextField(
        blank=True,
        default="incomplete files provided or invalid information or pharmavy is not legal",
        verbose_name=_("Rejection Reason"),
        help_text=_("Reason for rejecting the pharmacy application")
    )

    application_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        default='pending',
        verbose_name=_("Application Status"),
        help_text=_("Status of the pharmacy application")
    )

    certificate_of_operation = models.FileField(
        upload_to=upload_image_path,
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'pdf']
            ),
            validate_certificate_size_format
        ],
        verbose_name=_("Certificate of Approve"),
        help_text=_("Certificate of the pharmacy")
    )

    class Meta:
        verbose_name_plural = "Pharmacies"
        ordering = ['name']

    def __str__(self):
        return self.name

    def calculate_distance_to(self, user_lat, user_lng):
        """Calculate distance from pharmacy to user location in kilometers"""
        if not self.latitude or not self.longitude:
            return None

        # Haversine formula
        R = 6371  # Earth's radius in kilometers

        lat1_rad = math.radians(float(user_lat))
        lon1_rad = math.radians(float(user_lng))
        lat2_rad = math.radians(float(self.latitude))
        lon2_rad = math.radians(float(self.longitude))

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        return round(R * c, 2)

    @property
    def total_drugs(self):
        return self.inventory.filter(status__in=['available', 'low_stock']).count()


class PharmacyRating(BaseModel):
    """
    Pharmacy rating model
    """
    pharmacy = models.ForeignKey(
        Pharmacy,
        on_delete=models.CASCADE,
        related_name='ratings',
        verbose_name=_("Pharmacy"),
        help_text=_("Pharmacy that received the rating")
    )

    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1),
                    MaxValueValidator(5)],
        verbose_name=_("Rating"),
        help_text=_("Rating given by the user")
    )

    review = models.TextField(
        blank=True,
        verbose_name=_("Review"),
        help_text=_("Review given by the user")
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("User"),
        help_text=_("User who gave the rating")
    )

    class Meta:
        unique_together = ['pharmacy', 'user']

    def __str__(self):
        return f"{self.pharmacy.name} - {self.rating}/5 by {self.user.username}"


class SavedPharmacy(BaseModel):
    """
    The pharmacies save by the user
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='saved_pharmacies',
        verbose_name=_("Saved Pharmacy"),
        help_text=_("Pharmacy saved by the user")
    )

    pharmacy = models.ForeignKey(
        Pharmacy,
        on_delete=models.CASCADE,
        related_name='saved_by',
        verbose_name=_("Pharmacy"),
        help_text=_("Pharmacy saved by the user")
    )

    saved_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Saved At"),
        help_text=_("Date and time when the pharmacy was saved")
    )

    class Meta:
        unique_together = ['user', 'pharmacy']
        verbose_name_plural = "Saved Pharmacies"

    def __str__(self):
        return f"{self.user.username} saved {self.pharmacy.name}"


class PharmacyVisit(BaseModel):
    """
    pharmacies visited by the user
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='visits',
        verbose_name=_("User"),
        help_text=_("User who visited the pharmacy")
    )

    pharmacy = models.ForeignKey(
        Pharmacy, on_delete=models.CASCADE,
        related_name='visits',
        verbose_name=_("Pharmacy"),
        help_text=_("Pharmacy visited by the user")
    )

    visited_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Visited at"),
        help_text=_("Date and time when the user visited the pharmacy")
    )

    def __str__(self):
        return f"{self.user.username} visited {self.pharmacy.name}"


class Inventory(BaseModel):
    """
    Inventory model for managing the pharmacy
    """
    AVAILABILITY_CHOICES = [
        ('available', 'Available'),
        ('low_stock', 'Low Stock'),
        ('out_of_stock', 'Out of Stock'),
        ('discontinued', 'Discontinued'),
    ]

    pharmacy = models.ForeignKey(
        Pharmacy,
        on_delete=models.CASCADE,
        related_name='inventory',
        verbose_name=_("Pharmacy"),
        help_text=_(" Inventory for a pharmacy ")
    )

    drug = models.ForeignKey(
        Drug,
        on_delete=models.CASCADE,
        related_name='inventory',
        verbose_name=_("Drug"),
        help_text=_("Drug in the inventory")
    )

    quantity = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of units of the drug available in the pharmacy inventory"),
        verbose_name=_("Quantity")
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_("Selling price per unit of the drug"),
        verbose_name=_("Price")
    )

    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        blank=True,
        null=True,
        help_text=_("Cost price per unit of the drug"),
        verbose_name=_("Cost Price")
    )

    status = models.CharField(
        max_length=20,
        choices=AVAILABILITY_CHOICES,
        default='available',
        help_text=_("Current availability status of the drug in inventory"),
        verbose_name=_("Status")
    )

    low_stock_threshold = models.PositiveIntegerField(
        default=10,
        help_text=_("Threshold below which the stock is considered low"),
        verbose_name=_("Low Stock Threshold")
    )

    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text=_("Expiry date of the drug batch"),
        verbose_name=_("Expiry Date")
    )

    batch_number = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Batch number of the drug"),
        verbose_name=_("Batch Number")
    )

    supplier = models.CharField(
        max_length=200,
        blank=True,
        help_text=_("Supplier of the drug"),
        verbose_name=_("Supplier")
    )

    notes = models.TextField(
        blank=True,
        help_text=_("Additional notes about the inventory item"),
        verbose_name=_("Notes")
    )

    last_updated = models.DateTimeField(
        auto_now=True,
        help_text=_("Timestamp when the inventory record was last updated"),
        verbose_name=_("Last Updated")
    )

    class Meta:
        unique_together = ['pharmacy', 'drug']
        verbose_name_plural = "Inventories"
        ordering = ['drug__name']

    def save(self, *args, **kwargs):
        if self.quantity == 0:
            self.status = 'out_of_stock'
        elif self.quantity <= self.low_stock_threshold:
            self.status = 'low_stock'
        else:
            self.status = 'available'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.pharmacy.name} - {self.drug.name}"

    @property
    def profit_margin(self):
        """Calculate profit margin if the cost price is available"""
        if self.cost_price and self.cost_price > 0:
            return ((self.price - self.cost_price) / self.cost_price) * 100
        return None

    @property
    def is_expired(self):
        """Check if the drug has expired"""
        if self.expiry_date:
            from django.utils import timezone
            return timezone.now().date() > self.expiry_date
        return False

    @property
    def days_until_expiry(self):
        """Days until expiry"""
        if self.expiry_date:
            from django.utils import timezone
            delta = self.expiry_date - timezone.now().date()
            return delta.days
        return None


class InventoryAlert(BaseModel):
    """
    Inventory alert model
    """
    ALERT_TYPES = [
        ('low_stock', 'Low Stock'),
        ('out_of_stock', 'Out of Stock'),
        ('expiring_soon', 'Expiring Soon'),
        ('expired', 'Expired'),
    ]

    inventory = models.ForeignKey(
        Inventory,
        on_delete=models.CASCADE,
        related_name='alerts',
        help_text=_("Inventory item associated with this alert"),
        verbose_name=_("Inventory")
    )
    alert_type = models.CharField(
        max_length=20,
        choices=ALERT_TYPES,
        help_text=_("Type of alert, e.g., low stock, out of stock, expiring soon, expired"),
        verbose_name=_("Alert Type")
    )
    message = models.TextField(
        help_text=_("Detailed message describing the alert"),
        verbose_name=_("Message")
    )
    is_resolved = models.BooleanField(
        default=False,
        help_text=_("Indicates whether the alert has been resolved"),
        verbose_name=_("Is Resolved")
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.inventory.pharmacy.name} - {self.alert_type}"


class PriceHistory(BaseModel):
    """
    Price history model
    """
    inventory = models.ForeignKey(
        Inventory,
        on_delete=models.CASCADE,
        related_name='price_history',
        help_text=_("Inventory item whose price was changed"),
        verbose_name=_("Inventory")
    )
    old_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("Previous price of the inventory item"),
        verbose_name=_("Old Price")
    )
    new_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("New price of the inventory item"),
        verbose_name=_("New Price")
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        help_text=_("User who changed the price"),
        verbose_name=_("Changed By")
    )
    changed_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Timestamp when the price was changed"),
        verbose_name=_("Changed At")
    )
    reason = models.CharField(
        max_length=200,
        blank=True,
        help_text=_("Reason for the price change"),
        verbose_name=_("Reason")
    )

    class Meta:
        ordering = ['-changed_at']
        verbose_name_plural = "Price Histories"

    def __str__(self):
        return f"{self.inventory.drug.name} price change: {self.old_price} → {self.new_price}"


class SearchHistory(models.Model):
    """
    Search history model
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='search_history',
        help_text=_("User who performed the search")
    )
    query = models.CharField(
        max_length=200,
        help_text=_("Search query entered by the user")
    )
    searched_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Timestamp when the search was performed")
    )

    class Meta:
        verbose_name_plural = "Search Histories"

    def __str__(self):
        return f"{self.user.username} searched '{self.query}'"
