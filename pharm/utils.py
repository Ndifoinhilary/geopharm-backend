# utils.py - Utility Functions
import math
from datetime import timedelta

from django.db import models
from django.db.models import Q, Count
from django.utils import timezone


def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points
    on earth (specified in decimal degrees)
    Returns distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    # Radius of earth in kilometers
    r = 6371
    return round(r * c, 2)


def filter_pharmacies_by_distance(pharmacies, user_lat, user_lng, max_distance):
    """
    Filter pharmacies by distance from user location
    """
    nearby_pharmacies = []

    for pharmacy in pharmacies:
        if pharmacy.latitude and pharmacy.longitude:
            distance = calculate_distance(user_lat, user_lng, pharmacy.latitude, pharmacy.longitude)
            if distance <= max_distance:
                pharmacy.distance = distance
                nearby_pharmacies.append(pharmacy)

    return sorted(nearby_pharmacies, key=lambda x: x.distance)


def get_drug_availability_status(drug):
    """
    Get availability status for a drug across all pharmacies
    """
    total_pharmacies = drug.inventory.count()
    available_pharmacies = drug.inventory.filter(status__in=['available', 'low_stock']).count()

    if total_pharmacies == 0:
        return 'not_stocked'
    elif available_pharmacies == 0:
        return 'out_of_stock_everywhere'
    elif available_pharmacies / total_pharmacies >= 0.7:
        return 'widely_available'
    else:
        return 'limited_availability'


def generate_inventory_alerts(pharmacy):
    """
    Generate alerts for inventory items that need attention
    """
    from .models import InventoryAlert

    alerts_created = 0

    # Check for low stock
    low_stock_items = pharmacy.inventory.filter(
        quantity__lte=models.F('low_stock_threshold'),
        quantity__gt=0
    )

    for item in low_stock_items:
        alert, created = InventoryAlert.objects.get_or_create(
            inventory=item,
            alert_type='low_stock',
            is_resolved=False,
            defaults={
                'message': f'{item.drug.name} is running low (only {item.quantity} left)'
            }
        )
        if created:
            alerts_created += 1

    # Check for out of stock
    out_of_stock_items = pharmacy.inventory.filter(quantity=0)

    for item in out_of_stock_items:
        alert, created = InventoryAlert.objects.get_or_create(
            inventory=item,
            alert_type='out_of_stock',
            is_resolved=False,
            defaults={
                'message': f'{item.drug.name} is out of stock'
            }
        )
        if created:
            alerts_created += 1

    # Check for expiring items
    next_month = timezone.now().date() + timedelta(days=30)
    expiring_items = pharmacy.inventory.filter(
        expiry_date__lte=next_month,
        expiry_date__gt=timezone.now().date()
    )

    for item in expiring_items:
        days_until_expiry = item.days_until_expiry
        alert, created = InventoryAlert.objects.get_or_create(
            inventory=item,
            alert_type='expiring_soon',
            is_resolved=False,
            defaults={
                'message': f'{item.drug.name} expires in {days_until_expiry} days'
            }
        )
        if created:
            alerts_created += 1

    return alerts_created


def calculate_inventory_value(pharmacy):
    """
    Calculate total inventory value for a pharmacy
    """
    from django.db.models import Sum, F

    total_value = pharmacy.inventory.aggregate(
        total=Sum(F('quantity') * F('price'))
    )['total'] or 0

    return total_value


def get_popular_drugs(limit=10):
    """
    Get most popular drugs based on search frequency and pharmacy stock
    """
    from .models import Drug, SearchHistory

    # Get drugs that are searched frequently
    popular_searches = SearchHistory.objects.values('query').annotate(
        search_count=Count('query')
    ).order_by('-search_count')[:limit * 2]

    search_queries = [item['query'] for item in popular_searches]

    # Find drugs matching these searches
    popular_drugs = Drug.objects.filter(
        Q(name__in=search_queries) | Q(generic_name__in=search_queries)
    ).annotate(
        pharmacy_count=Count('inventory', distinct=True)
    ).filter(pharmacy_count__gt=0).order_by('-pharmacy_count')[:limit]

    return popular_drugs


def format_price_change(old_price, new_price):
    """
    Format price change with amount and percentage
    """
    change_amount = new_price - old_price
    change_percentage = (change_amount / old_price) * 100 if old_price > 0 else 0

    return {
        'amount': change_amount,
        'percentage': round(change_percentage, 2),
        'direction': 'increase' if change_amount > 0 else 'decrease' if change_amount < 0 else 'no_change'
    }


def validate_coordinates(latitude, longitude):
    """
    Validate geographic coordinates
    """
    try:
        lat = float(latitude)
        lng = float(longitude)

        if not (-90 <= lat <= 90):
            return False, "Latitude must be between -90 and 90"

        if not (-180 <= lng <= 180):
            return False, "Longitude must be between -180 and 180"

        return True, None

    except (ValueError, TypeError):
        return False, "Invalid coordinate format"


def search_suggestions(query, limit=5):
    """
    Get search suggestions based on drug names
    """
    from .models import Drug

    if len(query) < 2:
        return []

    drugs = Drug.objects.filter(
        Q(name__icontains=query) | Q(generic_name__icontains=query)
    ).values_list('name', flat=True)[:limit]

    return list(drugs)
