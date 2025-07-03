from django.db.models import Min, Max, Avg
from rest_framework import serializers
from phonenumber_field.serializerfields import PhoneNumberField
from django.utils.translation import gettext as _
from pharm.models import Inventory, Pharmacy, Drug, DrugCategory, PriceHistory, InventoryAlert, PharmacyRating, \
    SearchHistory, SavedPharmacy


class DrugSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Drug
        fields = ['id', 'name', 'category', 'category_name', 'generic_name',
                  'manufacturer', 'dosage', 'drug_form', 'requires_prescription']


class PharmacySerializer(serializers.ModelSerializer):
    distance = serializers.SerializerMethodField()
    total_drugs = serializers.ReadOnlyField()
    phone = PhoneNumberField()

    class Meta:
        model = Pharmacy
        fields = ['id', 'name', 'address', 'latitude', 'longitude', 'phone', 'email', 'opening_hours',
                  'license_number', 'description', 'profile_image', 'logo',
                  'verified', 'working_hours', 'total_drugs', 'distance']

    def get_distance(self, obj):
        request = self.context.get('request')
        if request and 'lat' in request.query_params and 'lng' in request.query_params:
            try:
                user_lat = float(request.query_params['lat'])
                user_lng = float(request.query_params['lng'])
                return obj.calculate_distance_to(user_lat, user_lng)
            except (ValueError, TypeError):
                pass
        return None

    def validate(self, attrs):
        name = attrs.get('name')
        email = attrs.get('email')
        instance = getattr(self, 'instance', None)

        if name:
            qs = Pharmacy.objects.filter(name=name)
            if instance:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError({'name': _("Pharmacy with this name already exists")})

        if email:
            qs = Pharmacy.objects.filter(email=email)
            if instance:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError({'email': _("Pharmacy with this email already exists")})

        return attrs

class PharmacyApplicationSerializer(serializers.ModelSerializer):
    """
    Serializer for a user to apply and register his or her pharmacy in the system
    """

    phone = PhoneNumberField()
    class Meta:
        model = Pharmacy
        fields = ['name', 'address', 'city', 'latitude', 'longitude', 'phone', 'email', 'opening_hours',
                  'license_number', 'description', 'profile_image', 'logo', 'certificate_of_operation']


    def validate(self, attrs):
        certificate = attrs.get('certificate_of_operation')
        name = attrs.get('name')
        email = attrs.get('email')

        if not certificate:
            raise serializers.ValidationError({"certificate_of_operation": "Certificate of operation is required"})

        if not name:
            raise serializers.ValidationError({"name": "Pharmacy name is required"})

        if Pharmacy.objects.filter(name=name).exists():
            raise serializers.ValidationError({"name": "Pharmacy with this name already exists"})

        if Pharmacy.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": "Pharmacy with this email already exists"})

        return attrs


    def create(self, validated_data):
        """
        Create a new pharmacy instance
        :param validated_data: validated data from the serializer
        :return: created pharmacy instance
        """
        user = self.context['request'].user
        validated_data['owner'] = user

        return Pharmacy.objects.create(**validated_data)





class InventorySerializer(serializers.ModelSerializer):
    drug_name = serializers.CharField(source='drug.name', read_only=True)
    pharmacy_name = serializers.CharField(source='pharmacy.name', read_only=True)

    class Meta:
        model = Inventory
        fields = ['id', 'drug', 'drug_name', 'pharmacy', 'pharmacy_name',
                  'quantity', 'price', 'status', 'last_updated']


class DrugCategoryDetailSerializer(serializers.ModelSerializer):
    drugs_count = serializers.SerializerMethodField()
    average_price = serializers.SerializerMethodField()

    class Meta:
        model = DrugCategory
        fields = ['id', 'name', 'description', 'drugs_count', 'average_price', 'created_at']

    def get_drugs_count(self, obj):
        return obj.drugs.count()

    def get_average_price(self, obj):
        avg_price = Inventory.objects.filter(drug__category=obj).aggregate(Avg('price'))['price__avg']
        return round(avg_price, 2) if avg_price else None


class DrugDetailSerializer(serializers.ModelSerializer):
    category = DrugCategoryDetailSerializer(read_only=True)
    pharmacies_count = serializers.SerializerMethodField()
    min_price = serializers.SerializerMethodField()
    max_price = serializers.SerializerMethodField()
    average_price = serializers.SerializerMethodField()
    availability_status = serializers.SerializerMethodField()

    class Meta:
        model = Drug
        fields = [
            'id', 'name', 'category', 'description', 'generic_name',
            'manufacturer', 'dosage', 'drug_form', 'requires_prescription',
            'pharmacies_count', 'min_price', 'max_price', 'average_price',
            'availability_status', 'created_at', 'updated_at'
        ]

    def get_pharmacies_count(self, obj):
        return obj.inventory.filter(status__in=['available', 'low_stock']).count()

    def get_min_price(self, obj):
        min_price = obj.inventory.filter(status__in=['available', 'low_stock']).aggregate(Min('price'))['price__min']
        return min_price

    def get_max_price(self, obj):
        max_price = obj.inventory.filter(status__in=['available', 'low_stock']).aggregate(Max('price'))['price__max']
        return max_price

    def get_average_price(self, obj):
        avg_price = obj.inventory.filter(status__in=['available', 'low_stock']).aggregate(Avg('price'))['price__avg']
        return round(avg_price, 2) if avg_price else None

    def get_availability_status(self, obj):
        total_pharmacies = obj.inventory.count()
        available_pharmacies = obj.inventory.filter(status__in=['available', 'low_stock']).count()

        if total_pharmacies == 0:
            return 'not_stocked'
        elif available_pharmacies == 0:
            return 'out_of_stock_everywhere'
        elif available_pharmacies / total_pharmacies >= 0.7:
            return 'widely_available'
        else:
            return 'limited_availability'


class PharmacyDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed pharmacy information including owner, ratings, inventory, and recent visits.
    """
    owner_info = serializers.SerializerMethodField()
    rating_info = serializers.SerializerMethodField()
    inventory_summary = serializers.SerializerMethodField()
    recent_visits = serializers.SerializerMethodField()
    distance = serializers.SerializerMethodField()

    class Meta:
        model = Pharmacy
        fields = [
            'id', 'name', 'address', 'latitude', 'longitude', 'phone', 'email',
            'website', 'verified', 'working_hours', 'is_24_hours', 'license_number',
            'established_date', 'description', 'profile_image', 'owner_info',
            'rating_info', 'inventory_summary', 'recent_visits', 'distance',
            'created_at', 'updated_at'
        ]

    def get_owner_info(self, obj):
        return {
            'name': obj.owner.get_full_name() or obj.owner.username,
            'email': obj.owner.email,
            'joined_date': obj.owner.date_joined
        }

    def get_rating_info(self, obj):
        ratings = obj.ratings.all()
        if ratings:
            return {
                'average_rating': round(ratings.aggregate(Avg('rating'))['rating__avg'], 1),
                'total_ratings': ratings.count(),
                'rating_distribution': {
                    '5_star': ratings.filter(rating=5).count(),
                    '4_star': ratings.filter(rating=4).count(),
                    '3_star': ratings.filter(rating=3).count(),
                    '2_star': ratings.filter(rating=2).count(),
                    '1_star': ratings.filter(rating=1).count(),
                }
            }
        return None

    def get_inventory_summary(self, obj):
        inventory = obj.inventory.all()
        return {
            'total_drugs': inventory.count(),
            'available_drugs': inventory.filter(status='available').count(),
            'low_stock_drugs': inventory.filter(status='low_stock').count(),
            'out_of_stock_drugs': inventory.filter(status='out_of_stock').count(),
            'categories_count': inventory.values('drug__category').distinct().count(),
            'price_range': {
                'min': inventory.aggregate(Min('price'))['price__min'],
                'max': inventory.aggregate(Max('price'))['price__max']
            }
        }

    def get_recent_visits(self, obj):
        if self.context['request'].user.is_authenticated:
            recent_visits = obj.visits.filter(
                user=self.context['request'].user
            ).order_by('-visited_at')[:5]
            return [{'visited_at': visit.visited_at} for visit in recent_visits]
        return []

    def get_distance(self, obj):
        request = self.context.get('request')
        if request and 'lat' in request.query_params and 'lng' in request.query_params:
            try:
                user_lat = float(request.query_params['lat'])
                user_lng = float(request.query_params['lng'])
                return obj.calculate_distance_to(user_lat, user_lng)
            except (ValueError, TypeError):
                pass
        return None


class InventoryDetailSerializer(serializers.ModelSerializer):
    drug_info = DrugDetailSerializer(source='drug', read_only=True)
    pharmacy_info = serializers.SerializerMethodField()
    price_history = serializers.SerializerMethodField()
    alerts = serializers.SerializerMethodField()

    class Meta:
        model = Inventory
        fields = [
            'id', 'drug_info', 'pharmacy_info', 'quantity', 'price', 'cost_price',
            'status', 'low_stock_threshold', 'expiry_date', 'batch_number',
            'supplier', 'notes', 'profit_margin', 'is_expired', 'days_until_expiry',
            'price_history', 'alerts', 'last_updated', 'created_at'
        ]

    def get_pharmacy_info(self, obj):
        return {
            'id': obj.pharmacy.id,
            'name': obj.pharmacy.name,
            'address': obj.pharmacy.address,
            'verified': obj.pharmacy.verified
        }

    def get_price_history(self, obj):
        recent_changes = obj.price_history.all()[:5]
        return [{
            'old_price': change.old_price,
            'new_price': change.new_price,
            'changed_at': change.changed_at,
            'reason': change.reason
        } for change in recent_changes]

    def get_alerts(self, obj):
        active_alerts = obj.alerts.filter(is_resolved=False)
        return [{
            'id': alert.id,
            'alert_type': alert.alert_type,
            'message': alert.message,
            'created_at': alert.created_at
        } for alert in active_alerts]


class InventoryCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating inventory items"""

    class Meta:
        model = Inventory
        fields = [
            'drug', 'quantity', 'price', 'cost_price', 'low_stock_threshold',
            'expiry_date', 'batch_number', 'supplier', 'notes'
        ]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity cannot be negative")
        return value

    def validate(self, attrs):
        """Custom validation to check for duplicate drug in pharmacy"""
        drug = attrs.get('drug')

        pharmacy = self.context.get('pharmacy')
        if not pharmacy:
            raise serializers.ValidationError("Pharmacy context is required")


        if not self.instance:
            if Inventory.objects.filter(pharmacy=pharmacy, drug=drug).exists():
                raise serializers.ValidationError(
                    f"Drug '{drug.name}' already exists in your pharmacy inventory. "
                    "Please update the existing inventory item instead."
                )
        else:

            existing_same_drug = Inventory.objects.filter(
                pharmacy=pharmacy,
                drug=drug
            ).exclude(id=self.instance.id)

            if existing_same_drug.exists():
                raise serializers.ValidationError(
                    f"Drug '{drug.name}' already exists in your pharmacy inventory."
                )

        return attrs


class PharmacyListSerializer(serializers.ModelSerializer):
    distance = serializers.SerializerMethodField()
    rating_info = serializers.SerializerMethodField()

    class Meta:
        model = Pharmacy
        fields = [
            'id', 'name', 'address', 'latitude', 'longitude', 'phone',
            'verified', 'working_hours', 'is_24_hours', 'distance',
            'rating_info', 'total_drugs'
        ]

    def get_distance(self, obj):
        request = self.context.get('request')
        if request and 'lat' in request.query_params and 'lng' in request.query_params:
            try:
                user_lat = float(request.query_params['lat'])
                user_lng = float(request.query_params['lng'])
                return obj.calculate_distance_to(user_lat, user_lng)
            except (ValueError, TypeError):
                pass
        return None

    def get_rating_info(self, obj):
        ratings = obj.ratings.all()
        if ratings.exists():
            return {
                'average_rating': round(ratings.aggregate(Avg('rating'))['rating__avg'], 1),
                'total_ratings': ratings.count()
            }
        return None


class SavedPharmacySerializer(serializers.ModelSerializer):
    pharmacy = PharmacyListSerializer(read_only=True)
    pharmacy_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = SavedPharmacy
        fields = ['id', 'pharmacy', 'pharmacy_id', 'saved_at']


class SearchHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchHistory
        fields = ['id', 'query', 'searched_at']


class PharmacyRatingSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = PharmacyRating
        fields = ['id', 'rating', 'review', 'user_name', 'created_at']
        read_only_fields = ['user']


class InventoryAlertSerializer(serializers.ModelSerializer):
    drug_name = serializers.CharField(source='inventory.drug.name', read_only=True)

    class Meta:
        model = InventoryAlert
        fields = [
            'id', 'alert_type', 'message', 'drug_name',
            'is_resolved', 'created_at'
        ]


class PriceHistorySerializer(serializers.ModelSerializer):
    drug_name = serializers.CharField(source='inventory.drug.name', read_only=True)
    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)
    price_change = serializers.SerializerMethodField()

    class Meta:
        model = PriceHistory
        fields = [
            'id', 'drug_name', 'old_price', 'new_price', 'price_change',
            'changed_by_name', 'changed_at', 'reason'
        ]

    def get_price_change(self, obj):
        change = obj.new_price - obj.old_price
        percentage = (change / obj.old_price) * 100 if obj.old_price > 0 else 0
        return {
            'amount': change,
            'percentage': round(percentage, 2)
        }


class PatientDashboardSerializer(serializers.Serializer):
    total_searches = serializers.IntegerField()
    most_visited_pharmacies = PharmacyListSerializer(many=True)
    recent_searches = SearchHistorySerializer(many=True)
    saved_pharmacies_count = serializers.IntegerField()


class PharmacistDashboardSerializer(serializers.Serializer):
    total_drugs = serializers.IntegerField()
    out_of_stock_count = serializers.IntegerField()
    low_stock_count = serializers.IntegerField()
    total_visits = serializers.IntegerField()
    verification_status = serializers.BooleanField()
    total_inventory_value = serializers.DecimalField(max_digits=15, decimal_places=2)


# ===================== SEARCH RESULT SERIALIZERS =====================
class DrugSearchResultSerializer(serializers.Serializer):
    # Drug info
    drug_id = serializers.IntegerField()
    drug_name = serializers.CharField()
    drug_generic_name = serializers.CharField(required=False)
    drug_dosage = serializers.CharField(required=False)
    drug_category = serializers.CharField()
    requires_prescription = serializers.BooleanField()

    # Pharmacy info
    pharmacy_id = serializers.IntegerField()
    pharmacy_name = serializers.CharField()
    pharmacy_address = serializers.CharField()
    pharmacy_phone = serializers.CharField()
    pharmacy_verified = serializers.BooleanField()
    latitude = serializers.DecimalField(max_digits=10, decimal_places=8, required=False)
    longitude = serializers.DecimalField(max_digits=11, decimal_places=8, required=False)

    # Inventory info
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    quantity = serializers.IntegerField()
    status = serializers.CharField()
    distance = serializers.FloatField(required=False)
