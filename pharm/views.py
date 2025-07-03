import math
from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.contrib.gis.measure import Distance
from django.db.models import Q, Count, Avg, Sum, F
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, permissions, filters
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from .models import (
    Drug, Pharmacy, SavedPharmacy,
    PharmacyVisit, Inventory, SearchHistory, InventoryAlert, PriceHistory, PharmacyRating, DrugCategory
)
from .permissions import IsPharmacyOwner, IsAdminOrReadOnly, IsPatient
from .serializers import PharmacySerializer, DrugSerializer, DrugDetailSerializer, \
    InventoryDetailSerializer, PharmacyDetailSerializer, DrugCategoryDetailSerializer, InventoryAlertSerializer, \
    PharmacyApplicationSerializer, InventoryCreateUpdateSerializer

# ===================== SWAGGER SCHEMAS =====================
drug_response_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'id': openapi.Schema(type=openapi.TYPE_INTEGER),
        'name': openapi.Schema(type=openapi.TYPE_STRING),
        'generic_name': openapi.Schema(type=openapi.TYPE_STRING),
        'manufacturer': openapi.Schema(type=openapi.TYPE_STRING),
        'dosage': openapi.Schema(type=openapi.TYPE_STRING),
        'drug_form': openapi.Schema(type=openapi.TYPE_STRING),
        'category': openapi.Schema(type=openapi.TYPE_STRING),
        'requires_prescription': openapi.Schema(type=openapi.TYPE_BOOLEAN),
    }
)

pharmacy_response_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'id': openapi.Schema(type=openapi.TYPE_INTEGER),
        'name': openapi.Schema(type=openapi.TYPE_STRING),
        'address': openapi.Schema(type=openapi.TYPE_STRING),
        'phone': openapi.Schema(type=openapi.TYPE_STRING),
        'verified': openapi.Schema(type=openapi.TYPE_BOOLEAN),
        'is_24_hours': openapi.Schema(type=openapi.TYPE_BOOLEAN),
        'latitude': openapi.Schema(type=openapi.TYPE_NUMBER),
        'longitude': openapi.Schema(type=openapi.TYPE_NUMBER),
        'distance': openapi.Schema(type=openapi.TYPE_NUMBER, description="Distance in kilometers"),
        'avg_rating': openapi.Schema(type=openapi.TYPE_NUMBER),
        'total_ratings': openapi.Schema(type=openapi.TYPE_INTEGER),
    }
)

inventory_response_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'id': openapi.Schema(type=openapi.TYPE_INTEGER),
        'drug': drug_response_schema,
        'pharmacy': pharmacy_response_schema,
        'price': openapi.Schema(type=openapi.TYPE_NUMBER),
        'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
        'status': openapi.Schema(type=openapi.TYPE_STRING, enum=['available', 'low_stock', 'out_of_stock']),
        'expiry_date': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
        'low_stock_threshold': openapi.Schema(type=openapi.TYPE_INTEGER),
    }
)

# ===================== PATIENT DASHBOARD =====================
@swagger_auto_schema(
    method='get',
    operation_summary="Patient Dashboard",
    operation_description="Get personalized dashboard data for"
                          " a patient user including search history, "
                          "visited pharmacies, and saved pharmacies",
    responses={
        200: openapi.Response(
            description="Dashboard data successfully retrieved",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'total_searches': openapi.Schema(type=openapi.TYPE_INTEGER, description="Total number of searches performed"),
                    'most_visited_pharmacies': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=pharmacy_response_schema,
                        description="Top 5 most visited pharmacies"
                    ),
                    'recent_searches': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'query': openapi.Schema(type=openapi.TYPE_STRING),
                                'searched_at': openapi.Schema(type=openapi.TYPE_STRING, format='datetime'),
                            }
                        ),
                        description="Last 10 search queries"
                    ),
                    'saved_pharmacies_count': openapi.Schema(type=openapi.TYPE_INTEGER, description="Number of saved pharmacies"),
                }
            )
        ),
        401: "Unauthorized - User not authenticated",
        403: "Forbidden - User is not a patient",
    },
    tags=['Patient Dashboard']
)
@api_view(['GET'])
@permission_classes([IsPatient])
def user_dashboard(request):
    """Get personalized dashboard data for a patient user"""
    user = request.user

    total_searches = SearchHistory.objects.filter(user=user).count()

    most_visited = Pharmacy.objects.annotate(
        visit_count=Count('visits', filter=Q(visits__user=user))
    ).filter(visit_count__gt=0).order_by('-visit_count')[:5]

    recent_searches = SearchHistory.objects.filter(user=user).order_by('-searched_at')[:10]

    saved_count = SavedPharmacy.objects.filter(user=user).count()

    dashboard_data = {
        'total_searches': total_searches,
        'most_visited_pharmacies': PharmacySerializer(most_visited, many=True).data,
        'recent_searches': [{'id': s.id, 'query': s.query, 'searched_at': s.searched_at} for s in recent_searches],
        'saved_pharmacies_count': saved_count
    }

    return Response(dashboard_data)


# ===================== DRUG SEARCH =====================
@swagger_auto_schema(
    method='get',
    operation_summary="Search for Drugs",
    operation_description="Search for available drugs across"
                          " pharmacies with location-based filtering"
                          " and comprehensive search options",
    manual_parameters=[
        openapi.Parameter('q', openapi.IN_QUERY, description="Search query for drug name (required)", type=openapi.TYPE_STRING, required=True),
        openapi.Parameter('category', openapi.IN_QUERY, description="Filter by drug category name", type=openapi.TYPE_STRING),
        openapi.Parameter('lat', openapi.IN_QUERY, description="User's current latitude for distance calculation", type=openapi.TYPE_NUMBER),
        openapi.Parameter('lng', openapi.IN_QUERY, description="User's current longitude for distance calculation", type=openapi.TYPE_NUMBER),
        openapi.Parameter('max_distance', openapi.IN_QUERY, description="Maximum distance in kilometers (default: 50)", type=openapi.TYPE_NUMBER),
    ],
    responses={
        200: openapi.Response(
            description="List of drugs matching the search criteria",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'results': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'pharmacy_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'pharmacy_name': openapi.Schema(type=openapi.TYPE_STRING),
                                'pharmacy_address': openapi.Schema(type=openapi.TYPE_STRING),
                                'pharmacy_verified': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                'drug_name': openapi.Schema(type=openapi.TYPE_STRING),
                                'price': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'status': openapi.Schema(type=openapi.TYPE_STRING),
                                'distance': openapi.Schema(type=openapi.TYPE_NUMBER, description="Distance in km (if coordinates provided)"),
                            }
                        )
                    )
                }
            )
        ),
        400: "Bad request - missing required query parameter",
        401: "Unauthorized",
    },
    tags=['Drug Search']
)
@api_view(['GET'])
@permission_classes([IsPatient])
def search_drugs(request):
    """Search for available drugs across pharmacies"""
    query = request.GET.get('q', '')
    category = request.GET.get('category', '')
    user_lat = request.GET.get('lat')
    user_lng = request.GET.get('lng')
    max_distance = float(request.GET.get('max_distance', 50))

    if not query:
        return Response({'error': 'Query parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

    SearchHistory.objects.create(user=request.user, query=query)

    filters = Q(drug__name__icontains=query) & Q(status__in=['available', 'low_stock'])

    if category:
        filters &= Q(drug__category__name__icontains=category)

    inventory_items = Inventory.objects.filter(filters).select_related(
        'pharmacy', 'drug', 'drug__category'
    )

    results = []
    for item in inventory_items:
        pharmacy = item.pharmacy
        distance = None

        if user_lat and user_lng and pharmacy.latitude and pharmacy.longitude:
            distance = pharmacy.calculate_distance_to(float(user_lat), float(user_lng))

            if distance and distance > max_distance:
                continue

        result = {
            'pharmacy_id': pharmacy.id,
            'pharmacy_name': pharmacy.name,
            'pharmacy_address': pharmacy.address,
            'pharmacy_phone': pharmacy.phone,
            'pharmacy_verified': pharmacy.verified,
            'latitude': pharmacy.latitude,
            'longitude': pharmacy.longitude,
            'drug_name': item.drug.name,
            'price': item.price,
            'quantity': item.quantity,
            'status': item.status,
        }

        if distance is not None:
            result['distance'] = distance

        results.append(result)

    if user_lat and user_lng:
        results.sort(key=lambda x: x.get('distance', float('inf')))
    else:
        results.sort(key=lambda x: x['pharmacy_name'])

    return Response({'count': len(results), 'results': results})


# ===================== PHARMACIST DASHBOARD =====================
@swagger_auto_schema(
    method='get',
    operation_summary="Pharmacist Dashboard",
    operation_description="Get comprehensive dashboard data "
                          "for pharmacy owners including inventory stats, "
                          "visits, and verification status",
    responses={
        200: openapi.Response(
            description="Dashboard data for pharmacy operations",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'total_drugs': openapi.Schema(type=openapi.TYPE_INTEGER, description="Total number of drugs in inventory"),
                    'out_of_stock_count': openapi.Schema(type=openapi.TYPE_INTEGER, description="Number of out-of-stock items"),
                    'low_stock_count': openapi.Schema(type=openapi.TYPE_INTEGER, description="Number of low-stock items"),
                    'total_visits': openapi.Schema(type=openapi.TYPE_INTEGER, description="Total pharmacy visits"),
                    'verification_status': openapi.Schema(type=openapi.TYPE_BOOLEAN, description="Pharmacy verification status"),
                }
            )
        ),
        400: "Bad request - No pharmacy associated with user",
        401: "Unauthorized",
        403: "Forbidden - User is not a pharmacy owner",
    },
    tags=['Pharmacist Dashboard']
)
@api_view(['GET'])
@permission_classes([IsPharmacyOwner])
def pharmacist_dashboard(request):
    """Get pharmacist dashboard data for a pharmacy owner"""
    try:
        pharmacy = request.user.pharmacy
    except Pharmacy.DoesNotExist:
        return Response({'error': 'No pharmacy associated with this user'}, status=status.HTTP_400_BAD_REQUEST)

    total_drugs = pharmacy.inventory.count()
    out_of_stock = pharmacy.inventory.filter(status='out_of_stock').count()
    low_stock = pharmacy.inventory.filter(status='low_stock').count()
    total_visits = pharmacy.visits.count()

    dashboard_data = {
        'total_drugs': total_drugs,
        'out_of_stock_count': out_of_stock,
        'low_stock_count': low_stock,
        'total_visits': total_visits,
        'verification_status': pharmacy.verified
    }

    return Response(dashboard_data)


# ===================== DRUG VIEWSET =====================
class DrugViewSet(ModelViewSet):
    """
    ViewSet for managing drugs with search and autocomplete functionality
    (Only admin users can create drugs in the system)
    """
    queryset = Drug.objects.select_related('category')
    serializer_class = DrugSerializer
    permission_classes = [IsAdminOrReadOnly]

    @swagger_auto_schema(
        operation_summary="List Drugs",
        operation_description="Retrieve a list of all drugs with optional search filtering",
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, description="Search by drug name or generic name", type=openapi.TYPE_STRING),
        ],
        responses={
            200: openapi.Response("List of drugs", schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=drug_response_schema
            ))
        },
        tags=['Drugs']
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Create Drug",
        operation_description="Create a new drug (Admin only)",
        request_body=DrugSerializer,
        responses={
            201: openapi.Response("Drug created successfully", drug_response_schema),
            400: "Bad request - Invalid data",
            401: "Unauthorized",
            403: "Forbidden - Admin access required",
        },
        tags=['Drugs']
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def get_queryset(self):
        queryset = self.queryset
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(generic_name__icontains=search)
            )
        return queryset.order_by('name')

    @swagger_auto_schema(
        method='get',
        operation_summary="Drug Autocomplete",
        operation_description="Get autocomplete suggestions "
                              "for drug names (minimum 2 characters required)",
        manual_parameters=[
            openapi.Parameter('q', openapi.IN_QUERY, description="Search query (minimum 2 characters)", type=openapi.TYPE_STRING, required=True),
        ],
        responses={
            200: openapi.Response(
                description="List of matching drug suggestions",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'name': openapi.Schema(type=openapi.TYPE_STRING),
                            'label': openapi.Schema(type=openapi.TYPE_STRING, description="Formatted name with dosage"),
                        }
                    )
                )
            ),
        },
        tags=['Drugs']
    )
    @action(detail=False, methods=['get'])
    def autocomplete(self, request):
        """Get autocomplete suggestions for drug names"""
        query = request.query_params.get('q', '').strip()
        if len(query) < 2:
            return Response([])

        drugs = Drug.objects.filter(
            Q(name__icontains=query) | Q(generic_name__icontains=query)
        ).select_related('category')[:10]

        results = [
            {'id': drug.id, 'name': drug.name, 'label': f"{drug.name} - {drug.dosage}" if drug.dosage else drug.name}
            for drug in drugs]
        return Response(results)


@swagger_auto_schema(
    method='get',
    operation_summary="Drug Name Autocomplete",
    operation_description="Standalone autocomplete endpoint "
                          "for drug names with minimum 2 character requirement",
    manual_parameters=[
        openapi.Parameter('q', openapi.IN_QUERY, description="Search query (minimum 2 characters)", type=openapi.TYPE_STRING, required=True),
    ],
    responses={
        200: openapi.Response(
            description="List of matching drug names",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'name': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            )
        ),
    },
    tags=['Drug Search']
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def drug_autocomplete(request):
    """Standalone drug autocomplete functionality"""
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return Response([])

    drugs = Drug.objects.filter(name__icontains=query)[:10]
    results = [{'id': drug.id, 'name': drug.name} for drug in drugs]
    return Response(results)



class PharmacyViewSet(ModelViewSet):
    """
    ViewSet for managing pharmacies with location-based features
    1. Creating or applying with your pharmacy details
    """
    queryset = Pharmacy.objects.all()
    serializer_class = PharmacySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):

        if self.action == 'create':
            return PharmacyApplicationSerializer
        return PharmacySerializer

    def get_permissions(self):
        """
        Custom permission logic to allow all authenticated users to view pharmacies,
        but restrict creation to pharmacy owners.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsPharmacyOwner]
        else:
            self.permission_classes = [permissions.IsAuthenticated]
        return super().get_permissions()

    @swagger_auto_schema(
        operation_summary="Retrieve Pharmacy Details",
        operation_description="Get detailed information about a specific "
                              "pharmacy. For patients, this automatically records a visit.",
        responses={
            200: openapi.Response("Pharmacy details", pharmacy_response_schema),
            404: "Pharmacy not found",
        },
        tags=['Pharmacies']
    )
    def retrieve(self, request, *args, **kwargs):
        """Retrieve pharmacy details and record visit for patients"""
        pharmacy = self.get_object()

        if getattr(request.user, 'is_patient', False):
            PharmacyVisit.objects.get_or_create(
                user=request.user,
                pharmacy=pharmacy
            )

        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        method='get',
        operation_summary="Find Nearby Pharmacies",
        operation_description="Get pharmacies within a specified radius of the user's location",
        manual_parameters=[
            openapi.Parameter('lat', openapi.IN_QUERY, description="User's latitude", type=openapi.TYPE_NUMBER, required=True),
            openapi.Parameter('lng', openapi.IN_QUERY, description="User's longitude", type=openapi.TYPE_NUMBER, required=True),
            openapi.Parameter('radius', openapi.IN_QUERY, description="Search radius in kilometers (default: 10)", type=openapi.TYPE_NUMBER),
        ],
        responses={
            200: openapi.Response(
                description="List of nearby pharmacies",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=pharmacy_response_schema
                )
            ),
            400: "Bad request - lat and lng parameters required",
        },
        tags=['Pharmacies']
    )
    @action(detail=False, methods=['get'])
    def nearby(self, request):
        """Find pharmacies within a specified radius"""
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        radius = float(request.query_params.get('radius', 10))

        if not lat or not lng:
            return Response({'error': 'lat and lng parameters are required'}, status=status.HTTP_400_BAD_REQUEST)

        pharmacies = Pharmacy.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False
        )

        serializer = self.get_serializer(pharmacies, many=True, context={'request': request})
        return Response(serializer.data)


# ===================== PHARMACY SEARCH =====================
@swagger_auto_schema(
    method='get',
    operation_summary="Basic Pharmacy Search",
    operation_description="Search pharmacies with location-based filtering and basic options",
    manual_parameters=[
        openapi.Parameter('q', openapi.IN_QUERY, description="Search query for pharmacy name or address", type=openapi.TYPE_STRING),
        openapi.Parameter('lat', openapi.IN_QUERY, description="User's current latitude", type=openapi.TYPE_NUMBER),
        openapi.Parameter('lng', openapi.IN_QUERY, description="User's current longitude", type=openapi.TYPE_NUMBER),
        openapi.Parameter('radius', openapi.IN_QUERY, description="Maximum search radius in kilometers (default: 50)", type=openapi.TYPE_NUMBER),
        openapi.Parameter('verified', openapi.IN_QUERY, description="Filter for verified pharmacies only", type=openapi.TYPE_BOOLEAN),
        openapi.Parameter('24_hours', openapi.IN_QUERY, description="Filter for 24-hour pharmacies only", type=openapi.TYPE_BOOLEAN),
    ],
    responses={
        200: openapi.Response(
            description="List of pharmacies matching search criteria",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'results': openapi.Schema(type=openapi.TYPE_ARRAY, items=pharmacy_response_schema),
                    'search_params': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'query': openapi.Schema(type=openapi.TYPE_STRING),
                            'coordinates_provided': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'radius_km': openapi.Schema(type=openapi.TYPE_NUMBER),
                            'verified_only': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            '24_hours_only': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        }
                    ),
                }
            )
        ),
    },
    tags=['Pharmacy Search']
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def pharmacy_search(request):
    """
    Search pharmacies with optional location-based filtering
    """
    query = request.GET.get('q', '').strip()
    user_lat = request.GET.get('lat')
    user_lng = request.GET.get('lng')
    max_radius = float(request.GET.get('radius', 50))
    verified_only = request.GET.get('verified', '').lower() == 'true'
    hours_24_only = request.GET.get('24_hours', '').lower() == 'true'

    pharmacies = Pharmacy.objects.all()

    if query:
        pharmacies = pharmacies.filter(
            Q(name__icontains=query) |
            Q(address__icontains=query) |
            Q(description__icontains=query)
        )

    if verified_only:
        pharmacies = pharmacies.filter(verified=True)

    if hours_24_only:
        pharmacies = pharmacies.filter(is_24_hours=True)

    results = []
    if user_lat and user_lng:
        try:
            user_latitude = float(user_lat)
            user_longitude = float(user_lng)

            pharmacies_with_coords = pharmacies.filter(
                latitude__isnull=False,
                longitude__isnull=False
            )

            for pharmacy in pharmacies_with_coords:
                distance = calculate_distance(
                    user_latitude, user_longitude,
                    float(pharmacy.latitude), float(pharmacy.longitude)
                )

                if distance <= max_radius:
                    pharmacy.distance = distance
                    results.append(pharmacy)

            results.sort(key=lambda x: x.distance)

        except (ValueError, TypeError):
            results = list(pharmacies)
    else:
        results = list(pharmacies)

    serializer = PharmacySerializer(results, many=True, context={'request': request})

    return Response({
        'count': len(results),
        'results': serializer.data,
        'search_params': {
            'query': query,
            'coordinates_provided': bool(user_lat and user_lng),
            'radius_km': max_radius if user_lat and user_lng else None,
            'verified_only': verified_only,
            '24_hours_only': hours_24_only
        }
    })


def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points
    on earth (specified in decimal degrees) using Haversine formula
    Returns distance in kilometers
    """
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    R = 6371
    return round(R * c, 2)


@swagger_auto_schema(
    method='get',
    operation_summary="Enhanced Pharmacy Search with PostGIS",
    operation_description="High-performance geospatial search using "
                          "PostGIS for better accuracy and performance",
    manual_parameters=[
        openapi.Parameter('q', openapi.IN_QUERY, description="Search query for pharmacy name or address", type=openapi.TYPE_STRING),
        openapi.Parameter('lat', openapi.IN_QUERY, description="User's current latitude", type=openapi.TYPE_NUMBER, required=True),
        openapi.Parameter('lng', openapi.IN_QUERY, description="User's current longitude", type=openapi.TYPE_NUMBER, required=True),
        openapi.Parameter('radius', openapi.IN_QUERY, description="Maximum search radius in kilometers (default: 50)", type=openapi.TYPE_NUMBER),
    ],
    responses={
        200: openapi.Response(
            description="List of pharmacies sorted by distance using PostGIS",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'results': openapi.Schema(type=openapi.TYPE_ARRAY, items=pharmacy_response_schema),
                }
            )
        ),
    },
    tags=['Pharmacy Search']
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def pharmacy_search_with_postgis(request):
    """
    Enhanced pharmacy search using PostGIS for better geospatial queries
    Note: Requires PostGIS extension and GeoDjango setup
    """
    query = request.GET.get('q', '').strip()
    user_lat = request.GET.get('lat')
    user_lng = request.GET.get('lng')
    max_radius = float(request.GET.get('radius', 50))

    pharmacies = Pharmacy.objects.all()

    if query:
        pharmacies = pharmacies.filter(
            Q(name__icontains=query) | Q(address__icontains=query)
        )

    if user_lat and user_lng:
        try:
            user_location = Point(float(user_lng), float(user_lat))

            pharmacies = pharmacies.filter(
                location__distance_lte=(user_location, Distance(km=max_radius))
            ).annotate(
                distance=Distance('location', user_location)
            ).order_by('distance')

        except (ValueError, TypeError):
            pass

    serializer = PharmacySerializer(pharmacies, many=True, context={'request': request})
    return Response({'count': pharmacies.count(), 'results': serializer.data})


@swagger_auto_schema(
    method='get',
    operation_summary="Advanced Pharmacy Search",
    operation_description="Comprehensive pharmacy search with rating"
                          " filters, drug availability, and multiple sorting options",
    manual_parameters=[
        openapi.Parameter('q', openapi.IN_QUERY, description="Search query for pharmacy name, address, or owner", type=openapi.TYPE_STRING),
        openapi.Parameter('lat', openapi.IN_QUERY, description="User's current latitude", type=openapi.TYPE_NUMBER),
        openapi.Parameter('lng', openapi.IN_QUERY, description="User's current longitude", type=openapi.TYPE_NUMBER),
        openapi.Parameter('radius', openapi.IN_QUERY, description="Maximum search radius in kilometers (default: 50)", type=openapi.TYPE_NUMBER),
        openapi.Parameter('min_rating', openapi.IN_QUERY, description="Minimum average rating (1-5)", type=openapi.TYPE_NUMBER),
        openapi.Parameter('verified', openapi.IN_QUERY, description="Filter for verified pharmacies only", type=openapi.TYPE_BOOLEAN),
        openapi.Parameter('24_hours', openapi.IN_QUERY, description="Filter for 24-hour pharmacies only", type=openapi.TYPE_BOOLEAN),
        openapi.Parameter('has_drug', openapi.IN_QUERY, description="Filter pharmacies that stock specific drug (name or ID)", type=openapi.TYPE_STRING),
        openapi.Parameter('sort_by', openapi.IN_QUERY, description="Sort results by", type=openapi.TYPE_STRING, enum=["distance", "rating", "name", "newest"]),
    ],
    responses={
        200: openapi.Response(
            description="Advanced search results with metadata",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'results': openapi.Schema(type=openapi.TYPE_ARRAY, items=pharmacy_response_schema),
                    'search_metadata': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'query': openapi.Schema(type=openapi.TYPE_STRING),
                            'filters_applied': openapi.Schema(type=openapi.TYPE_OBJECT),
                            'total_before_location_filter': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    ),
                }
            )
        ),
    },
    tags=['Pharmacy Search']
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def advanced_pharmacy_search(request):
    """
    Advanced pharmacy search with comprehensive filtering and sorting
    """
    query = request.GET.get('q', '').strip()
    user_lat = request.GET.get('lat')
    user_lng = request.GET.get('lng')
    max_radius = float(request.GET.get('radius', 50))
    min_rating = request.GET.get('min_rating')
    verified_only = request.GET.get('verified', '').lower() == 'true'
    hours_24_only = request.GET.get('24_hours', '').lower() == 'true'
    has_drug = request.GET.get('has_drug')
    sort_by = request.GET.get('sort_by', 'distance')

    pharmacies = Pharmacy.objects.select_related('owner').prefetch_related('ratings', 'inventory')

    if query:
        pharmacies = pharmacies.filter(
            Q(name__icontains=query) |
            Q(address__icontains=query) |
            Q(description__icontains=query) |
            Q(owner__first_name__icontains=query) |
            Q(owner__last_name__icontains=query)
        )

    if verified_only:
        pharmacies = pharmacies.filter(verified=True)

    if hours_24_only:
        pharmacies = pharmacies.filter(is_24_hours=True)

    if min_rating:
        try:
            min_rating_value = float(min_rating)
            pharmacies = pharmacies.annotate(
                avg_rating=Avg('ratings__rating')
            ).filter(avg_rating__gte=min_rating_value)
        except ValueError:
            pass

    if has_drug:
        try:
            drug_id = int(has_drug)
            pharmacies = pharmacies.filter(
                inventory__drug_id=drug_id,
                inventory__status__in=['available', 'low_stock']
            ).distinct()
        except ValueError:
            pharmacies = pharmacies.filter(
                inventory__drug__name__icontains=has_drug,
                inventory__status__in=['available', 'low_stock']
            ).distinct()

    results = []
    if user_lat and user_lng:
        try:
            user_latitude = float(user_lat)
            user_longitude = float(user_lng)

            pharmacies_with_coords = pharmacies.filter(
                latitude__isnull=False,
                longitude__isnull=False
            )

            for pharmacy in pharmacies_with_coords:
                distance = calculate_distance(
                    user_latitude, user_longitude,
                    float(pharmacy.latitude), float(pharmacy.longitude)
                )

                if distance <= max_radius:
                    pharmacy.distance = distance

                    ratings = pharmacy.ratings.all()
                    if ratings:
                        pharmacy.avg_rating = sum(r.rating for r in ratings) / len(ratings)
                        pharmacy.total_ratings = len(ratings)
                    else:
                        pharmacy.avg_rating = None
                        pharmacy.total_ratings = 0

                    results.append(pharmacy)
        except (ValueError, TypeError):
            results = list(pharmacies)
    else:
        results = list(pharmacies)

        for pharmacy in results:
            ratings = pharmacy.ratings.all()
            if ratings:
                pharmacy.avg_rating = sum(r.rating for r in ratings) / len(ratings)
                pharmacy.total_ratings = len(ratings)
            else:
                pharmacy.avg_rating = None
                pharmacy.total_ratings = 0

    if sort_by == 'distance' and user_lat and user_lng:
        results.sort(key=lambda x: getattr(x, 'distance', float('inf')))
    elif sort_by == 'rating':
        results.sort(key=lambda x: getattr(x, 'avg_rating', 0), reverse=True)
    elif sort_by == 'name':
        results.sort(key=lambda x: x.name)
    elif sort_by == 'newest':
        results.sort(key=lambda x: x.created_at, reverse=True)

    serializer = PharmacySerializer(results, many=True, context={'request': request})

    return Response({
        'count': len(results),
        'results': serializer.data,
        'search_metadata': {
            'query': query,
            'filters_applied': {
                'location_based': bool(user_lat and user_lng),
                'radius_km': max_radius if user_lat and user_lng else None,
                'min_rating': min_rating,
                'verified_only': verified_only,
                '24_hours_only': hours_24_only,
                'has_drug': has_drug,
                'sort_by': sort_by
            },
            'total_before_location_filter': pharmacies.count() if not (user_lat and user_lng) else None
        }
    })



class DrugCategoryManagementViewSet(ModelViewSet):
    """
    ViewSet for managing drug categories with related drugs and pharmacies
     (Only admin users can create a drug category in the system)
    """
    queryset = DrugCategory.objects.all()
    serializer_class = DrugCategoryDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']

    def get_permissions(self):
        """
        Custom permission logic to allow all authenticated users to view categories
        but restrict creation to admin users.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [permissions.IsAdminUser]
        else:
            self.permission_classes = [permissions.IsAuthenticated]
        return super().get_permissions()


    @swagger_auto_schema(
        method='get',
        operation_summary="Get Drugs in Category",
        operation_description="Retrieve all drugs belonging to a"
                              " specific category with optional search",
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, description="Search drugs by name or generic name", type=openapi.TYPE_STRING),
        ],
        responses={
            200: openapi.Response(
                description="List of drugs in the category",
                schema=openapi.Schema(type=openapi.TYPE_ARRAY, items=drug_response_schema)
            )
        },
        tags=['Drug Categories']
    )
    @action(detail=True, methods=['get'])
    def drugs(self, request, pk=None):
        """Get all drugs in this category"""
        category = self.get_object()
        drugs = category.drugs.all()

        search = request.query_params.get('search')
        if search:
            drugs = drugs.filter(
                Q(name__icontains=search) | Q(generic_name__icontains=search)
            )

        serializer = DrugDetailSerializer(drugs, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        method='get',
        operation_summary="Get Pharmacies with Category Drugs",
        operation_description="Find pharmacies that stock drugs from this category",
        responses={
            200: openapi.Response(
                description="List of pharmacies with category drugs",
                schema=openapi.Schema(type=openapi.TYPE_ARRAY, items=pharmacy_response_schema)
            )
        },
        tags=['Drug Categories']
    )
    @action(detail=True, methods=['get'])
    def pharmacies(self, request, pk=None):
        """Get pharmacies that stock drugs from this category"""
        category = self.get_object()
        pharmacies = Pharmacy.objects.filter(
            inventory__drug__category=category,
            inventory__status__in=['available', 'low_stock']
        ).distinct()

        serializer = PharmacySerializer(pharmacies, many=True, context={'request': request})
        return Response(serializer.data)



class DrugDiscoveryViewSet(ReadOnlyModelViewSet):
    """
    Advanced drug management with comprehensive filtering and analysis
    """
    queryset = Drug.objects.select_related('category').prefetch_related('inventory')
    serializer_class = DrugDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'generic_name', 'manufacturer']
    ordering_fields = ['name', 'created_at']

    @swagger_auto_schema(
        operation_summary="List Drugs with Advanced Filtering",
        operation_description="Get drugs with comprehensive filtering options",
        manual_parameters=[
            openapi.Parameter('category', openapi.IN_QUERY, description="Filter by category ID", type=openapi.TYPE_INTEGER),
            openapi.Parameter('prescription', openapi.IN_QUERY, description="Filter by prescription requirement", type=openapi.TYPE_BOOLEAN),
            openapi.Parameter('available_only', openapi.IN_QUERY, description="Show only available drugs", type=openapi.TYPE_BOOLEAN),
            openapi.Parameter('min_price', openapi.IN_QUERY, description="Minimum price filter", type=openapi.TYPE_NUMBER),
            openapi.Parameter('max_price', openapi.IN_QUERY, description="Maximum price filter", type=openapi.TYPE_NUMBER),
        ],
        tags=['Advanced Drug Management']
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = self.queryset

        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category_id=category)

        prescription = self.request.query_params.get('prescription')
        if prescription is not None:
            requires_prescription = prescription.lower() == 'true'
            queryset = queryset.filter(requires_prescription=requires_prescription)

        available_only = self.request.query_params.get('available_only')
        if available_only == 'true':
            queryset = queryset.filter(
                inventory__status__in=['available', 'low_stock']
            ).distinct()

        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(inventory__price__gte=min_price).distinct()
        if max_price:
            queryset = queryset.filter(inventory__price__lte=max_price).distinct()

        return queryset

    @swagger_auto_schema(
        method='get',
        operation_summary="Get Pharmacies Stocking Drug",
        operation_description="Find pharmacies that have this drug in stock with"
                              " pricing and distance information",
        manual_parameters=[
            openapi.Parameter('lat', openapi.IN_QUERY, description="User's latitude for distance calculation", type=openapi.TYPE_NUMBER),
            openapi.Parameter('lng', openapi.IN_QUERY, description="User's longitude for distance calculation", type=openapi.TYPE_NUMBER),
            openapi.Parameter('max_distance', openapi.IN_QUERY, description="Maximum distance in km (default: 50)", type=openapi.TYPE_NUMBER),
            openapi.Parameter('sort_by', openapi.IN_QUERY, description="Sort by price or distance", type=openapi.TYPE_STRING, enum=['price', 'distance']),
        ],
        responses={
            200: openapi.Response(
                description="List of pharmacies with pricing and availability",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'pharmacy_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'pharmacy_name': openapi.Schema(type=openapi.TYPE_STRING),
                            'pharmacy_address': openapi.Schema(type=openapi.TYPE_STRING),
                            'pharmacy_verified': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'price': openapi.Schema(type=openapi.TYPE_NUMBER),
                            'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'status': openapi.Schema(type=openapi.TYPE_STRING),
                            'distance': openapi.Schema(type=openapi.TYPE_NUMBER),
                        }
                    )
                )
            )
        },
        tags=['Advanced Drug Management']
    )
    @action(detail=True, methods=['get'])
    def pharmacies(self, request, pk=None):
        """Get pharmacies that stock this drug"""
        drug = self.get_object()
        user_lat = request.query_params.get('lat')
        user_lng = request.query_params.get('lng')
        max_distance = float(request.query_params.get('max_distance', 50))

        inventory_items = drug.inventory.filter(
            status__in=['available', 'low_stock']
        ).select_related('pharmacy')

        results = []
        for item in inventory_items:
            pharmacy = item.pharmacy
            distance = None

            if user_lat and user_lng and pharmacy.latitude and pharmacy.longitude:
                distance = pharmacy.calculate_distance_to(float(user_lat), float(user_lng))
                if distance > max_distance:
                    continue

            result = {
                'pharmacy_id': pharmacy.id,
                'pharmacy_name': pharmacy.name,
                'pharmacy_address': pharmacy.address,
                'pharmacy_verified': pharmacy.verified,
                'price': item.price,
                'quantity': item.quantity,
                'status': item.status,
                'distance': distance
            }
            results.append(result)

        sort_by = request.query_params.get('sort_by', 'distance')
        if sort_by == 'price':
            results.sort(key=lambda x: x['price'])
        elif sort_by == 'distance' and user_lat and user_lng:
            results.sort(key=lambda x: x['distance'] or float('inf'))

        return Response(results)

    @swagger_auto_schema(
        method='get',
        operation_summary="Drug Price Analysis",
        operation_description="Get comprehensive pricing analytics for a"
                              " specific drug across all pharmacies",
        responses={
            200: openapi.Response(
                description="Price analysis data",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'min_price': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'max_price': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'average_price': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'median_price': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'price_variance': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'pharmacies_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'price_distribution': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'below_average': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'above_average': openapi.Schema(type=openapi.TYPE_INTEGER),
                            }
                        ),
                    }
                )
            )
        },
        tags=['Advanced Drug Management']
    )
    @action(detail=True, methods=['get'])
    def price_analysis(self, request, pk=None):
        """Get price analysis for this drug"""
        drug = self.get_object()
        inventory_items = drug.inventory.filter(status__in=['available', 'low_stock'])

        if not inventory_items.exists():
            return Response({'message': 'No pricing data available'})

        prices = [item.price for item in inventory_items]

        analysis = {
            'min_price': min(prices),
            'max_price': max(prices),
            'average_price': sum(prices) / len(prices),
            'median_price': sorted(prices)[len(prices) // 2],
            'price_variance': max(prices) - min(prices),
            'pharmacies_count': len(prices),
            'price_distribution': {
                'below_average': len([p for p in prices if p < sum(prices) / len(prices)]),
                'above_average': len([p for p in prices if p > sum(prices) / len(prices)])
            }
        }

        return Response(analysis)



class PharmacyProfileViewSet(ReadOnlyModelViewSet):
    """
    Advanced pharmacy management with ratings, reviews, and analytics
    """
    queryset = Pharmacy.objects.select_related('owner').prefetch_related('ratings', 'inventory')
    serializer_class = PharmacyDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'address', 'phone']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        queryset = self.queryset

        verified = self.request.query_params.get('verified')
        if verified is not None:
            queryset = queryset.filter(verified=verified.lower() == 'true')

        is_24_hours = self.request.query_params.get('24_hours')
        if is_24_hours is not None:
            queryset = queryset.filter(is_24_hours=is_24_hours.lower() == 'true')

        min_rating = self.request.query_params.get('min_rating')
        if min_rating:
            queryset = queryset.annotate(
                avg_rating=Avg('ratings__rating')
            ).filter(avg_rating__gte=float(min_rating))

        return queryset

    @swagger_auto_schema(
        method='post',
        operation_summary="Rate Pharmacy",
        operation_description="Add or update a rating and review for a pharmacy (patients only)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'rating': openapi.Schema(type=openapi.TYPE_INTEGER, minimum=1, maximum=5, description="Rating from 1-5"),
                'review': openapi.Schema(type=openapi.TYPE_STRING, description="Optional review text"),
            },
            required=['rating']
        ),
        responses={
            200: "Rating updated successfully",
            201: "Rating created successfully",
            400: "Invalid rating data",
            403: "Forbidden - Patients only",
        },
        tags=['Advanced Pharmacy Management']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsPatient])
    def rate(self, request, pk=None):
        """Rate and review a pharmacy"""
        pharmacy = self.get_object()

        serializer_data = {
            'rating': request.data.get('rating'),
            'review': request.data.get('review', '')
        }

        existing_rating = PharmacyRating.objects.filter(
            pharmacy=pharmacy, user=request.user
        ).first()

        if existing_rating:
            for key, value in serializer_data.items():
                if value is not None:
                    setattr(existing_rating, key, value)
            existing_rating.save()

            return Response({
                'message': 'Rating updated successfully',
                'rating': existing_rating.rating,
                'review': existing_rating.review
            })
        else:
            rating = PharmacyRating.objects.create(
                pharmacy=pharmacy,
                user=request.user,
                **serializer_data
            )

            return Response({
                'message': 'Rating created successfully',
                'rating': rating.rating,
                'review': rating.review
            }, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        method='get',
        operation_summary="Get Pharmacy Reviews",
        operation_description="Retrieve all reviews for a pharmacy with pagination",
        manual_parameters=[
            openapi.Parameter('page', openapi.IN_QUERY, description="Page number (default: 1)", type=openapi.TYPE_INTEGER),
        ],
        responses={
            200: openapi.Response(
                description="Paginated list of reviews",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'results': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'user_name': openapi.Schema(type=openapi.TYPE_STRING),
                                    'rating': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'review': openapi.Schema(type=openapi.TYPE_STRING),
                                    'created_at': openapi.Schema(type=openapi.TYPE_STRING, format='datetime'),
                                }
                            )
                        ),
                        'has_next': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    }
                )
            )
        },
        tags=['Advanced Pharmacy Management']
    )
    @action(detail=True, methods=['get'])
    def reviews(self, request, pk=None):
        """Get all reviews for this pharmacy"""
        pharmacy = self.get_object()
        reviews = pharmacy.ratings.select_related('user').order_by('-created_at')

        page_size = 10
        page = int(request.query_params.get('page', 1))
        start = (page - 1) * page_size
        end = start + page_size

        results = []
        for review in reviews[start:end]:
            results.append({
                'id': review.id,
                'user_name': review.user.get_full_name() or review.user.username,
                'rating': review.rating,
                'review': review.review,
                'created_at': review.created_at
            })

        return Response({
            'count': reviews.count(),
            'results': results,
            'has_next': end < reviews.count()
        })

    @swagger_auto_schema(
        method='get',
        operation_summary="Pharmacy Analytics",
        operation_description="Get comprehensive analytics for a pharmacy"
                              " including visits, inventory, and ratings",
        responses={
            200: openapi.Response(
                description="Comprehensive pharmacy analytics",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'visits': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'total_visits': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'visits_today': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'visits_this_week': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'visits_this_month': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'unique_visitors': openapi.Schema(type=openapi.TYPE_INTEGER),
                            }
                        ),
                        'inventory': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'total_drugs': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'available_drugs': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'low_stock_drugs': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'out_of_stock_drugs': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'total_inventory_value': openapi.Schema(type=openapi.TYPE_NUMBER),
                            }
                        ),
                        'ratings': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'average_rating': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'total_ratings': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'rating_distribution': openapi.Schema(type=openapi.TYPE_OBJECT),
                            }
                        ),
                    }
                )
            )
        },
        tags=['Advanced Pharmacy Management']
    )
    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """Get pharmacy analytics"""
        pharmacy = self.get_object()

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        visits = pharmacy.visits.all()
        visit_analytics = {
            'total_visits': visits.count(),
            'visits_today': visits.filter(visited_at__date=today).count(),
            'visits_this_week': visits.filter(visited_at__date__gte=week_ago).count(),
            'visits_this_month': visits.filter(visited_at__date__gte=month_ago).count(),
            'unique_visitors': visits.values('user').distinct().count()
        }

        inventory = pharmacy.inventory.all()
        inventory_analytics = {
            'total_drugs': inventory.count(),
            'available_drugs': inventory.filter(status='available').count(),
            'low_stock_drugs': inventory.filter(status='low_stock').count(),
            'out_of_stock_drugs': inventory.filter(status='out_of_stock').count(),
            'total_inventory_value': inventory.aggregate(
                total=Sum(F('quantity') * F('price'))
            )['total'] or 0
        }

        ratings = pharmacy.ratings.all()
        rating_analytics = {
            'average_rating': ratings.aggregate(Avg('rating'))['rating__avg'] or 0,
            'total_ratings': ratings.count(),
            'rating_distribution': {
                str(i): ratings.filter(rating=i).count() for i in range(1, 6)
            }
        }

        return Response({
            'visits': visit_analytics,
            'inventory': inventory_analytics,
            'ratings': rating_analytics
        })


class InventoryManagementViewSet(ModelViewSet):
    """
    Complete inventory management viewset for pharmacy owners
    """
    permission_classes = [IsPharmacyOwner]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['drug__name', 'drug__generic_name', 'batch_number']
    ordering_fields = ['drug__name', 'quantity', 'price', 'last_updated', 'expiry_date']
    ordering = ['-last_updated']  # Default ordering

    def get_serializer_class(self):
        """Return the appropriate serializer based on action"""
        if self.action in ['create', 'update', 'partial_update']:
            return InventoryCreateUpdateSerializer
        return InventoryDetailSerializer

    def get_serializer_context(self):
        """Add pharmacy to serializer context"""
        context = super().get_serializer_context()
        try:
            context['pharmacy'] = self.request.user.pharmacy
        except AttributeError:
            context['pharmacy'] = None
        return context

    def get_queryset(self):
        """Get inventory items for the authenticated pharmacy owner"""
        try:
            pharmacy = self.request.user.pharmacy
            return Inventory.objects.filter(pharmacy=pharmacy).select_related(
                'drug', 'drug__category', 'pharmacy'
            )
        except AttributeError:
            return Inventory.objects.none()

    def perform_create(self, serializer):
        """Set the pharmacy when creating an inventory item"""
        try:
            pharmacy = self.request.user.pharmacy
            serializer.save(pharmacy=pharmacy)
        except AttributeError:
            raise ValidationError("User must have an associated pharmacy")

    @swagger_auto_schema(
        operation_summary="List Inventory Items",
        operation_description="Get all inventory items for the authenticated pharmacy owner",
        manual_parameters=[
            openapi.Parameter(
                'search',
                openapi.IN_QUERY,
                description="Search by drug name, generic name, or batch number",
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'ordering',
                openapi.IN_QUERY,
                description="Order by: drug__name, quantity, price, last_updated, expiry_date",
                type=openapi.TYPE_STRING
            ),
        ],
        responses={
            200: InventoryDetailSerializer(many=True),
            401: "Unauthorized - Authentication required",
            403: "Forbidden - Must be a pharmacy owner",
        },
        tags=['Inventory Management']
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Create Inventory Item",
        operation_description="Add a new drug to the pharmacy's inventory."
                              " The pharmacy is automatically set from the authenticated user."
                              " Operation is perform by the pharmacy owner.",
        request_body=InventoryCreateUpdateSerializer,
        responses={
            201: InventoryDetailSerializer,
            400: "Bad request - Invalid data or drug already exists",
            401: "Unauthorized - Authentication required",
            403: "Forbidden - Must be a pharmacy owner",
        },
        tags=['Inventory Management']
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Get Inventory Item",
        operation_description="Retrieve details of a specific inventory item",
        responses={
            200: InventoryDetailSerializer,
            404: "Inventory item not found",
            403: "Forbidden - Can only access your own inventory",
        },
        tags=['Inventory Management']
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Update Inventory Item",
        operation_description="Update an existing inventory item completely",
        request_body=InventoryCreateUpdateSerializer,
        responses={
            200: InventoryDetailSerializer,
            400: "Bad request - Invalid data",
            404: "Inventory item not found",
            403: "Forbidden - Can only update your own inventory",
        },
        tags=['Inventory Management']
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Partially Update Inventory Item",
        operation_description="Partially update an existing inventory item",
        request_body=InventoryCreateUpdateSerializer,
        responses={
            200: InventoryDetailSerializer,
            400: "Bad request - Invalid data",
            404: "Inventory item not found",
            403: "Forbidden - Can only update your own inventory",
        },
        tags=['Inventory Management']
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Delete Inventory Item",
        operation_description="Remove an inventory item from the pharmacy",
        responses={
            204: "Inventory item deleted successfully",
            404: "Inventory item not found",
            403: "Forbidden - Can only delete your own inventory",
        },
        tags=['Inventory Management']
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    @swagger_auto_schema(
        operation_summary="Get Low Stock Items",
        operation_description="Get all inventory items that are low in stock or out of stock",
        responses={200: InventoryDetailSerializer(many=True)},
        tags=['Inventory Management']
    )
    def low_stock(self, request):
        """Get items with low stock or out of stock"""
        low_stock_items = self.get_queryset().filter(
            status__in=['low_stock', 'out_of_stock']
        )
        serializer = self.get_serializer(low_stock_items, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    @swagger_auto_schema(
        operation_summary="Get Expiring Items",
        operation_description="Get inventory items expiring within specified days (default: 30)",
        manual_parameters=[
            openapi.Parameter(
                'days',
                openapi.IN_QUERY,
                description="Number of days from now to check for expiry (default: 30)",
                type=openapi.TYPE_INTEGER
            ),
        ],
        responses={200: InventoryDetailSerializer(many=True)},
        tags=['Inventory Management']
    )
    def expiring_soon(self, request):
        """Get items expiring within specified days"""
        days = int(request.query_params.get('days', 30))
        from django.utils import timezone
        cutoff_date = timezone.now().date() + timedelta(days=days)

        expiring_items = self.get_queryset().filter(
            expiry_date__lte=cutoff_date,
            expiry_date__isnull=False
        )
        serializer = self.get_serializer(expiring_items, many=True)
        return Response(serializer.data)

class InventoryAnalyticsViewSet(ReadOnlyModelViewSet):
    """
    Advanced inventory management with analytics and bulk operations
    """
    serializer_class = InventoryDetailSerializer
    permission_classes = [IsPharmacyOwner]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['drug__name', 'drug__generic_name', 'supplier']
    ordering_fields = ['drug__name', 'quantity', 'price', 'last_updated']

    def get_queryset(self):
        try:
            pharmacy = self.request.user.pharmacy
            queryset = Inventory.objects.filter(pharmacy=pharmacy).select_related(
                'drug', 'drug__category', 'pharmacy'
            ).prefetch_related('alerts', 'price_history')

            status_filter = self.request.query_params.get('status')
            if status_filter:
                queryset = queryset.filter(status=status_filter)

            category = self.request.query_params.get('category')
            if category:
                queryset = queryset.filter(drug__category_id=category)

            low_stock = self.request.query_params.get('low_stock')
            if low_stock == 'true':
                queryset = queryset.filter(quantity__lte=F('low_stock_threshold'))

            expiring_soon = self.request.query_params.get('expiring_soon')
            if expiring_soon == 'true':
                cutoff_date = timezone.now().date() + timedelta(days=30)
                queryset = queryset.filter(
                    expiry_date__lte=cutoff_date,
                    expiry_date__gt=timezone.now().date()
                )

            min_price = self.request.query_params.get('min_price')
            max_price = self.request.query_params.get('max_price')
            if min_price:
                queryset = queryset.filter(price__gte=min_price)
            if max_price:
                queryset = queryset.filter(price__lte=max_price)

            return queryset
        except:
            return Inventory.objects.none()

    @swagger_auto_schema(
        method='get',
        operation_summary="Inventory Dashboard Analytics",
        operation_description="Get comprehensive inventory analytics "
                              "including value, status breakdown, and alerts",
        responses={
            200: openapi.Response(
                description="Comprehensive inventory analytics",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'overview': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'total_items': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'total_value': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'total_profit': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'average_item_value': openapi.Schema(type=openapi.TYPE_NUMBER),
                            }
                        ),
                        'status_breakdown': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                                    'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'total_value': openapi.Schema(type=openapi.TYPE_NUMBER),
                                }
                            )
                        ),
                        'category_breakdown': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'drug__category__name': openapi.Schema(type=openapi.TYPE_STRING),
                                    'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'total_quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'avg_price': openapi.Schema(type=openapi.TYPE_NUMBER),
                                }
                            )
                        ),
                        'alerts': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'low_stock_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'expiring_soon_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                            }
                        ),
                        'recent_price_changes': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'drug_name': openapi.Schema(type=openapi.TYPE_STRING),
                                    'old_price': openapi.Schema(type=openapi.TYPE_NUMBER),
                                    'new_price': openapi.Schema(type=openapi.TYPE_NUMBER),
                                    'changed_at': openapi.Schema(type=openapi.TYPE_STRING, format='datetime'),
                                }
                            )
                        ),
                    }
                )
            )
        },
        tags=['Advanced Inventory Management']
    )
    @action(detail=False, methods=['get'])
    def dashboard_analytics(self, request):
        """Get comprehensive inventory analytics"""
        try:
            pharmacy = request.user.pharmacy
            inventory = Inventory.objects.filter(pharmacy=pharmacy)

            total_items = inventory.count()
            total_value = inventory.aggregate(
                total=Sum(F('quantity') * F('price'))
            )['total'] or 0

            status_stats = inventory.values('status').annotate(
                count=Count('id'),
                total_value=Sum(F('quantity') * F('price'))
            )

            category_stats = inventory.values('drug__category__name').annotate(
                count=Count('id'),
                total_quantity=Sum('quantity'),
                avg_price=Avg('price')
            ).order_by('-count')

            low_stock_items = inventory.filter(quantity__lte=F('low_stock_threshold'))

            next_month = timezone.now().date() + timedelta(days=30)
            expiring_items = inventory.filter(
                expiry_date__lte=next_month,
                expiry_date__gt=timezone.now().date()
            )

            profit_items = inventory.filter(cost_price__isnull=False)
            total_profit = sum([
                (item.price - item.cost_price) * item.quantity
                for item in profit_items
            ])

            recent_price_changes = PriceHistory.objects.filter(
                inventory__pharmacy=pharmacy
            ).select_related('inventory__drug').order_by('-changed_at')[:10]

            return Response({
                'overview': {
                    'total_items': total_items,
                    'total_value': total_value,
                    'total_profit': total_profit,
                    'average_item_value': total_value / total_items if total_items > 0 else 0
                },
                'status_breakdown': list(status_stats),
                'category_breakdown': list(category_stats),
                'alerts': {
                    'low_stock_count': low_stock_items.count(),
                    'expiring_soon_count': expiring_items.count()
                },
                'recent_price_changes': [{
                    'drug_name': change.inventory.drug.name,
                    'old_price': change.old_price,
                    'new_price': change.new_price,
                    'changed_at': change.changed_at
                } for change in recent_price_changes]
            })

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='post',
        operation_summary="Bulk Price Update",
        operation_description="Update prices for multiple inventory "
                              "items using percentage or fixed amount adjustment",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'inventory_ids': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_INTEGER)),
                'update_type': openapi.Schema(type=openapi.TYPE_STRING, enum=['percentage', 'fixed']),
                'adjustment': openapi.Schema(type=openapi.TYPE_NUMBER, description="Percentage or fixed amount"),
                'reason': openapi.Schema(type=openapi.TYPE_STRING, description="Reason for price change"),
            },
            required=['inventory_ids', 'adjustment']
        ),
        responses={
            200: openapi.Response(
                description="Bulk update completed",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'updated_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    }
                )
            ),
            400: "Bad request - Invalid data",
        },
        tags=['Advanced Inventory Management']
    )
    @action(detail=False, methods=['post'])
    def bulk_price_update(self, request):
        """Bulk update prices with percentage or fixed amount"""
        try:
            pharmacy = request.user.pharmacy
            inventory_ids = request.data.get('inventory_ids', [])
            update_type = request.data.get('update_type', 'percentage')
            adjustment = Decimal(str(request.data.get('adjustment', 0)))
            reason = request.data.get('reason', 'Bulk price update')

            if not inventory_ids:
                return Response({'error': 'No inventory IDs provided'}, status=status.HTTP_400_BAD_REQUEST)

            inventory_items = Inventory.objects.filter(
                id__in=inventory_ids,
                pharmacy=pharmacy
            )

            updated_count = 0
            for item in inventory_items:
                old_price = item.price

                if update_type == 'percentage':
                    new_price = old_price * (1 + adjustment / 100)
                else:
                    new_price = old_price + adjustment

                new_price = max(new_price, Decimal('0.01'))

                item.price = new_price
                item.save()

                PriceHistory.objects.create(
                    inventory=item,
                    old_price=old_price,
                    new_price=new_price,
                    changed_by=request.user,
                    reason=reason
                )

                updated_count += 1

            return Response({
                'message': f'Successfully updated prices for {updated_count} items',
                'updated_count': updated_count
            })

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        method='get',
        operation_summary="Expiry Report",
        operation_description="Get detailed report of expired and expiring inventory items",
        responses={
            200: openapi.Response(
                description="Comprehensive expiry report",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'expired': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'estimated_loss': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'items': openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'drug_name': openapi.Schema(type=openapi.TYPE_STRING),
                                        'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'expiry_date': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
                                        'days_until_expiry': openapi.Schema(type=openapi.TYPE_INTEGER),
                                        'estimated_loss': openapi.Schema(type=openapi.TYPE_NUMBER),
                                    }
                                )
                            ),
                            }
                        ),
                        'expiring_this_week': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'estimated_loss': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'items': openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'drug_name': openapi.Schema(type=openapi.TYPE_STRING),
                                            'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'expiry_date': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
                                            'days_until_expiry': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'estimated_loss': openapi.Schema(type=openapi.TYPE_NUMBER),
                                        }
                                    )
                                ),
                            }
                        ),
                        'expiring_this_month': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'estimated_loss': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'items': openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'drug_name': openapi.Schema(type=openapi.TYPE_STRING),
                                            'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'expiry_date': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
                                            'days_until_expiry': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'estimated_loss': openapi.Schema(type=openapi.TYPE_NUMBER),
                                        }
                                    )
                                ),
                            }
                        ),
                    }
                )
            )
        },
        tags=['Advanced Inventory Management']
    )
    @action(detail=False, methods=['get'])
    def expiry_report(self, request):
        """Get a detailed expiry report"""
        try:
            pharmacy = request.user.pharmacy
            today = timezone.now().date()

            expired = pharmacy.inventory.filter(expiry_date__lt=today)

            next_week = today + timedelta(days=7)
            expiring_week = pharmacy.inventory.filter(
                expiry_date__gte=today,
                expiry_date__lte=next_week
            )

            next_month = today + timedelta(days=30)
            expiring_month = pharmacy.inventory.filter(
                expiry_date__gte=today,
                expiry_date__lte=next_month
            )

            def serialize_items(items):
                return [{
                    'id': item.id,
                    'drug_name': item.drug.name,
                    'quantity': item.quantity,
                    'expiry_date': item.expiry_date,
                    'days_until_expiry': item.days_until_expiry,
                    'estimated_loss': item.price * item.quantity
                } for item in items]

            return Response({
                'expired': {
                    'count': expired.count(),
                    'estimated_loss': sum(item.price * item.quantity for item in expired),
                    'items': serialize_items(expired)
                },
                'expiring_this_week': {
                    'count': expiring_week.count(),
                    'estimated_loss': sum(item.price * item.quantity for item in expiring_week),
                    'items': serialize_items(expiring_week)
                },
                'expiring_this_month': {
                    'count': expiring_month.count(),
                    'estimated_loss': sum(item.price * item.quantity for item in expiring_month),
                    'items': serialize_items(expiring_month)
                }
            })

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ===================== ANALYTICS & REPORTING VIEWS =====================
@swagger_auto_schema(
    method='get',
    operation_summary="Patient Analytics",
    operation_description="Get comprehensive usage"
                          " analytics for patient "
                          "users including search patterns "
                          "and pharmacy interactions",
    responses={
        200: openapi.Response(
            description="Patient usage analytics",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'search_analytics': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'total_searches': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'popular_searches': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'query': openapi.Schema(type=openapi.TYPE_STRING),
                            'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    )
                ),
                            'search_frequency': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'date': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
                            'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    )
                ),
                        }
                    ),
                    'pharmacy_interaction': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'total_visits': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'saved_pharmacies': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'frequent_pharmacies': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'pharmacy__name': openapi.Schema(type=openapi.TYPE_STRING),
                        'visit_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    }
                )
            ),
                        }
                    ),
                }
            )
        ),
        403: "Forbidden - Patients only",
    },
    tags=['Analytics']
)
@api_view(['GET'])
@permission_classes([IsPatient])
def patient_analytics(request):
    """Get patient usage analytics"""
    user = request.user

    searches = SearchHistory.objects.filter(user=user)
    total_searches = searches.count()

    popular_searches = searches.values('query').annotate(
        count=Count('query')
    ).order_by('-count')[:10]

    search_by_date = searches.extra(
        select={'date': 'date(searched_at)'}
    ).values('date').annotate(count=Count('id')).order_by('-date')[:30]

    visits = PharmacyVisit.objects.filter(user=user)
    saved_pharmacies = SavedPharmacy.objects.filter(user=user)

    frequent_pharmacies = visits.values('pharmacy__name').annotate(
        visit_count=Count('pharmacy')
    ).order_by('-visit_count')[:5]

    return Response({
        'search_analytics': {
            'total_searches': total_searches,
            'popular_searches': list(popular_searches),
            'search_frequency': list(search_by_date)
        },
        'pharmacy_interaction': {
            'total_visits': visits.count(),
            'saved_pharmacies': saved_pharmacies.count(),
            'frequent_pharmacies': list(frequent_pharmacies)
        }
    })


@swagger_auto_schema(
    method='get',
    operation_summary="Pharmacy Analytics",
    operation_description="Get comprehensive analytics for pharmacy owners"
                          " including visits, inventory performance,"
                          " and search analytics",
    responses={
        200: openapi.Response(
            description="Comprehensive pharmacy analytics",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'visits': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'total_visits': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'visits_today': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'visits_this_week': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'visits_this_month': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'unique_visitors': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'daily_visits': openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'date': openapi.Schema(type=openapi.TYPE_STRING, format='date'),
                                        'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    }
                                )
                            ),
                        }
                    ),
                    'inventory': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'total_items': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'total_value': openapi.Schema(type=openapi.TYPE_NUMBER),
                            'low_stock_alerts': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'out_of_stock': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'category_distribution': openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'drug__category__name': openapi.Schema(type=openapi.TYPE_STRING),
                                        'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    }
                                )
                            )
                        }
                    ),
                    'searches': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'relevant_searches': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'popular_drug_searches': openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'query': openapi.Schema(type=openapi.TYPE_STRING),
                                        'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    }
                                )
                            )
                        }
                    ),
                    'revenue': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'potential_revenue': openapi.Schema(type=openapi.TYPE_NUMBER),
                            'potential_profit': openapi.Schema(type=openapi.TYPE_NUMBER),
                            'profit_margin_avg': openapi.Schema(type=openapi.TYPE_NUMBER),
                        }
                    ),
                }
            )
        ),
        400: "Bad request",
        403: "Forbidden - Pharmacy owners only",
    },
    tags=['Analytics']
)
@api_view(['GET'])
@permission_classes([IsPharmacyOwner])
def pharmacy_analytics(request):
    """Get comprehensive pharmacy analytics"""
    try:
        pharmacy = request.user.pharmacy

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        visits = pharmacy.visits.all()
        visit_analytics = {
            'total_visits': visits.count(),
            'visits_today': visits.filter(visited_at__date=today).count(),
            'visits_this_week': visits.filter(visited_at__date__gte=week_ago).count(),
            'visits_this_month': visits.filter(visited_at__date__gte=month_ago).count(),
            'unique_visitors': visits.values('user').distinct().count(),
            'daily_visits': list(visits.extra(
                select={'date': 'date(visited_at)'}
            ).values('date').annotate(count=Count('id')).order_by('-date')[:30])
        }

        inventory = pharmacy.inventory.all()
        inventory_analytics = {
            'total_items': inventory.count(),
            'total_value': inventory.aggregate(
                total=Sum(F('quantity') * F('price'))
            )['total'] or 0,
            'low_stock_alerts': inventory.filter(quantity__lte=F('low_stock_threshold')).count(),
            'out_of_stock': inventory.filter(status='out_of_stock').count(),
            'category_distribution': list(inventory.values('drug__category__name').annotate(
                count=Count('id')
            ).order_by('-count'))
        }

        drug_searches = SearchHistory.objects.filter(
            query__in=[item.drug.name for item in inventory]
        )
        search_analytics = {
            'relevant_searches': drug_searches.count(),
            'popular_drug_searches': list(drug_searches.values('query').annotate(
                count=Count('query')
            ).order_by('-count')[:10])
        }

        profit_items = inventory.filter(cost_price__isnull=False)
        revenue_analytics = {
            'potential_revenue': inventory.aggregate(
                total=Sum(F('quantity') * F('price'))
            )['total'] or 0,
            'potential_profit': sum([
                (item.price - item.cost_price) * item.quantity
                for item in profit_items
            ]),
            'profit_margin_avg': sum([
                item.profit_margin for item in profit_items if item.profit_margin
            ]) / len(profit_items) if profit_items else 0
        }

        return Response({
            'visits': visit_analytics,
            'inventory': inventory_analytics,
            'searches': search_analytics,
            'revenue': revenue_analytics
        })

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)



@swagger_auto_schema(
    method='get',
    operation_summary="Advanced Drug Search",
    operation_description="Comprehensive drug search with extensive "
                          "filtering, sorting, and grouping by drug type",
    manual_parameters=[
        openapi.Parameter('q', openapi.IN_QUERY, description="Search query for drug name, generic name, or manufacturer", type=openapi.TYPE_STRING),
        openapi.Parameter('category', openapi.IN_QUERY, description="Filter by drug category ID", type=openapi.TYPE_INTEGER),
        openapi.Parameter('min_price', openapi.IN_QUERY, description="Minimum price filter", type=openapi.TYPE_NUMBER),
        openapi.Parameter('max_price', openapi.IN_QUERY, description="Maximum price filter", type=openapi.TYPE_NUMBER),
        openapi.Parameter('requires_prescription', openapi.IN_QUERY, description="Filter by prescription requirement", type=openapi.TYPE_BOOLEAN),
        openapi.Parameter('drug_form', openapi.IN_QUERY, description="Filter by drug form (tablet, capsule, etc.)", type=openapi.TYPE_STRING),
        openapi.Parameter('manufacturer', openapi.IN_QUERY, description="Filter by manufacturer", type=openapi.TYPE_STRING),
        openapi.Parameter('sort_by', openapi.IN_QUERY, description="Sort results by", type=openapi.TYPE_STRING, enum=['relevance', 'price_asc', 'price_desc', 'name']),
        openapi.Parameter('lat', openapi.IN_QUERY, description="User's latitude for distance calculation", type=openapi.TYPE_NUMBER),
        openapi.Parameter('lng', openapi.IN_QUERY, description="User's longitude for distance calculation", type=openapi.TYPE_NUMBER),
        openapi.Parameter('max_distance', openapi.IN_QUERY, description="Maximum distance in kilometers (default: 50)", type=openapi.TYPE_NUMBER),
    ],
    responses={
        200: openapi.Response(
            description="Advanced search results grouped by drug",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER, description="Total results count"),
                    'drugs_found': openapi.Schema(type=openapi.TYPE_INTEGER, description="Number of unique drugs found"),
                    'results': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'drug_info': drug_response_schema,
                                'pharmacies': openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'pharmacy_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'pharmacy_name': openapi.Schema(type=openapi.TYPE_STRING),
                                            'pharmacy_address': openapi.Schema(type=openapi.TYPE_STRING),
                                            'pharmacy_verified': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                            'price': openapi.Schema(type=openapi.TYPE_NUMBER),
                                            'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                                            'status': openapi.Schema(type=openapi.TYPE_STRING),
                                            'distance': openapi.Schema(type=openapi.TYPE_NUMBER),
                                        }
                                    )
                                ),
                            }
                        )
                    ),
                }
            )
        ),
    },
    tags=['Advanced Search']
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def advanced_drug_search(request):
    """Advanced drug search with multiple filters and sorting"""
    query = request.GET.get('q', '')
    category = request.GET.get('category')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    requires_prescription = request.GET.get('requires_prescription')
    drug_form = request.GET.get('drug_form')
    manufacturer = request.GET.get('manufacturer')
    sort_by = request.GET.get('sort_by', 'relevance')
    user_lat = request.GET.get('lat')
    user_lng = request.GET.get('lng')
    max_distance = float(request.GET.get('max_distance', 50))

    if getattr(request.user, 'is_patient', False) and query:
        SearchHistory.objects.create(user=request.user, query=query)

    filters = Q(status__in=['available', 'low_stock'])

    if query:
        filters &= (Q(drug__name__icontains=query) |
                    Q(drug__generic_name__icontains=query) |
                    Q(drug__manufacturer__icontains=query))

    if category:
        filters &= Q(drug__category_id=category)

    if min_price:
        filters &= Q(price__gte=min_price)

    if max_price:
        filters &= Q(price__lte=max_price)

    if requires_prescription is not None:
        filters &= Q(drug__requires_prescription=requires_prescription.lower() == 'true')

    if drug_form:
        filters &= Q(drug__drug_form__icontains=drug_form)

    if manufacturer:
        filters &= Q(drug__manufacturer__icontains=manufacturer)

    inventory_items = Inventory.objects.filter(filters).select_related(
        'pharmacy', 'drug', 'drug__category'
    )

    results = []
    for item in inventory_items:
        pharmacy = item.pharmacy
        distance = None

        if user_lat and user_lng and pharmacy.latitude and pharmacy.longitude:
            distance = pharmacy.calculate_distance_to(float(user_lat), float(user_lng))
            if distance > max_distance:
                continue

        result = {
            'inventory_id': item.id,
            'drug_id': item.drug.id,
            'drug_name': item.drug.name,
            'drug_generic_name': item.drug.generic_name,
            'drug_manufacturer': item.drug.manufacturer,
            'drug_dosage': item.drug.dosage,
            'drug_form': item.drug.drug_form,
            'drug_category': item.drug.category.name,
            'requires_prescription': item.drug.requires_prescription,
            'pharmacy_id': pharmacy.id,
            'pharmacy_name': pharmacy.name,
            'pharmacy_address': pharmacy.address,
            'pharmacy_phone': pharmacy.phone,
            'pharmacy_verified': pharmacy.verified,
            'latitude': pharmacy.latitude,
            'longitude': pharmacy.longitude,
            'price': item.price,
            'quantity': item.quantity,
            'status': item.status,
            'distance': distance
        }
        results.append(result)

    if sort_by == 'price_asc':
        results.sort(key=lambda x: x['price'])
    elif sort_by == 'price_desc':
        results.sort(key=lambda x: x['price'], reverse=True)
    elif sort_by == 'distance' and user_lat and user_lng:
        results.sort(key=lambda x: x['distance'] or float('inf'))
    elif sort_by == 'name':
        results.sort(key=lambda x: x['drug_name'])

    drugs_map = {}
    for result in results:
        drug_id = result['drug_id']
        if drug_id not in drugs_map:
            drugs_map[drug_id] = {
                'drug_info': {
                    'id': result['drug_id'],
                    'name': result['drug_name'],
                    'generic_name': result['drug_generic_name'],
                    'manufacturer': result['drug_manufacturer'],
                    'dosage': result['drug_dosage'],
                    'form': result['drug_form'],
                    'category': result['drug_category'],
                    'requires_prescription': result['requires_prescription']
                },
                'pharmacies': []
            }

        drugs_map[drug_id]['pharmacies'].append({
            'pharmacy_id': result['pharmacy_id'],
            'pharmacy_name': result['pharmacy_name'],
            'pharmacy_address': result['pharmacy_address'],
            'pharmacy_verified': result['pharmacy_verified'],
            'price': result['price'],
            'quantity': result['quantity'],
            'status': result['status'],
            'distance': result['distance']
        })

    return Response({
        'count': len(results),
        'drugs_found': len(drugs_map),
        'results': list(drugs_map.values())
    })


@swagger_auto_schema(
    method='get',
    operation_summary="Drug Recommendations",
    operation_description="Get personalized drug recommendations "
                          "based on user search history and popular trends",
    responses={
        200: openapi.Response(
            description="Personalized or popular drug recommendations",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'type': openapi.Schema(type=openapi.TYPE_STRING, enum=['personalized', 'popular']),
                    'based_on_searches': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_STRING)
                    ),
                    'recommendations': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=drug_response_schema
                    ),
                }
            )
        ),
        403: "Forbidden - Patients only",
    },
    tags=['Advanced Search']
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def drug_recommendations(request):
    """Get drug recommendations based on user search history"""
    if not getattr(request.user, 'is_patient', False):
        return Response({'error': 'Only patients can get recommendations'}, status=status.HTTP_403_FORBIDDEN)

    user = request.user

    searches = SearchHistory.objects.filter(user=user).order_by('-searched_at')[:50]
    search_queries = [search.query.lower() for search in searches]

    if not search_queries:
        popular_drugs = Drug.objects.annotate(
            pharmacy_count=Count('inventory')
        ).filter(pharmacy_count__gt=0).order_by('-pharmacy_count')[:10]

        return Response({
            'type': 'popular',
            'recommendations': DrugDetailSerializer(popular_drugs, many=True).data
        })

    related_drugs = Drug.objects.filter(
        Q(name__icontains='|'.join(search_queries[:5])) |
        Q(category__in=Drug.objects.filter(
            name__icontains='|'.join(search_queries[:5])
        ).values_list('category', flat=True))
    ).exclude(
        name__in=search_queries
    ).annotate(
        pharmacy_count=Count('inventory')
    ).filter(pharmacy_count__gt=0).order_by('-pharmacy_count')[:10]

    return Response({
        'type': 'personalized',
        'based_on_searches': search_queries[:5],
        'recommendations': DrugDetailSerializer(related_drugs, many=True).data
    })


class InventoryAlertViewSet(ReadOnlyModelViewSet):
    """
    ViewSet for managing inventory alerts and notifications
    """
    serializer_class = InventoryAlertSerializer
    permission_classes = [IsPharmacyOwner]

    def get_queryset(self):
        try:
            pharmacy = self.request.user.pharmacy
            return InventoryAlert.objects.filter(
                inventory__pharmacy=pharmacy
            ).select_related('inventory__drug').order_by('-created_at')
        except:
            return InventoryAlert.objects.none()

    @swagger_auto_schema(
        method='post',
        operation_summary="Resolve Alert",
        operation_description="Mark a specific inventory alert as resolved",
        responses={
            200: openapi.Response(
                description="Alert resolved successfully",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={'message': openapi.Schema(type=openapi.TYPE_STRING)}
                )
            )
        },
        tags=['Alert Management']
    )
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Resolve an alert"""
        alert = self.get_object()
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.save()

        return Response({'message': 'Alert resolved successfully'})

    @swagger_auto_schema(
        method='post',
        operation_summary="Resolve All Alerts",
        operation_description="Mark all unresolved alerts for the pharmacy as resolved",
        responses={
            200: openapi.Response(
                description="All alerts resolved",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                        'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    }
                )
            )
        },
        tags=['Alert Management']
    )
    @action(detail=False, methods=['post'])
    def resolve_all(self, request):
        """Resolve all alerts"""
        try:
            pharmacy = request.user.pharmacy
            alerts = InventoryAlert.objects.filter(
                inventory__pharmacy=pharmacy,
                is_resolved=False
            )

            count = alerts.update(
                is_resolved=True,
                resolved_at=timezone.now()
            )

            return Response({
                'message': f'Resolved {count} alerts',
                'count': count
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method='post',
    operation_summary="Accept or Reject Pharmacy Application",
    operation_description="Admin endpoint to accept or reject pharmacy applications. "
                          "When accepted, the user becomes a pharmacy owner. "
                          "When rejected, the user remains a patient.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'action': openapi.Schema(
                type=openapi.TYPE_STRING,
                enum=['accept', 'reject'],
                description="Action to take on the pharmacy application"
            ),
            'rejection_reason': openapi.Schema(
                type=openapi.TYPE_STRING,
                description="Reason for rejection (required if action is 'reject')"
            ),
        },
        required=['action']
    ),
    responses={
        200: openapi.Response(
            description="Pharmacy application processed successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'pharmacy_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'user_role_updated': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                }
            )
        ),
        400: "Bad request - Invalid action or missing data",
        403: "Forbidden - Admin access required",
        404: "Pharmacy not found",
    },
    tags=['Admin Management']
)
@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def manage_pharmacy_application(request, pharmacy_id):
    """Accept or reject a pharmacy application (Admin only)"""
    try:
        pharmacy = Pharmacy.objects.get(id=pharmacy_id)
    except Pharmacy.DoesNotExist:
        return Response({'error': 'Pharmacy not found'}, status=status.HTTP_404_NOT_FOUND)

    action = request.data.get('action')
    if action not in ['accept', 'reject']:
        return Response(
            {'error': 'Invalid action. Must be "accept" or "reject"'},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = pharmacy.owner

    if action == 'accept':
        pharmacy.verified = True
        pharmacy.application_status = 'approved'
        pharmacy.save()

        user.is_patient = False
        user.is_pharmacy_owner = True
        user.save()

        # TODO: send email to the pharmacy owner updating him about the status of his pharmacy

        return Response({
            'message': f'Pharmacy "{pharmacy.name}" has been accepted successfully',
            'pharmacy_id': str(pharmacy.id),
            'status': 'accepted',
            'user_role_updated': True
        })

    elif action == 'reject':
        rejection_reason = request.data.get('rejection_reason', '')
        if not rejection_reason:
            return Response(
                {'error': 'Rejection reason is required when rejecting an application'},
                status=status.HTTP_400_BAD_REQUEST
            )

        pharmacy.verified = False
        pharmacy.application_status = 'rejected'
        pharmacy.rejection_reason = rejection_reason
        pharmacy.save()
        # TODO: send email to the pharmacy owner updating him about the status of his pharmacy
        user.is_patient = True
        user.is_pharmacy_owner = False
        user.save()

        return Response({
            'message': f'Pharmacy "{pharmacy.name}" has been rejected',
            'pharmacy_id': str(pharmacy.id),
            'status': 'rejected',
            'rejection_reason': rejection_reason,
            'user_role_updated': True
        })


@swagger_auto_schema(
    method='get',
    operation_summary="Get Pending Pharmacy Applications",
    operation_description="Get all pharmacy applications pending admin approval",
    manual_parameters=[
        openapi.Parameter(
            'status',
            openapi.IN_QUERY,
            description="Filter by verification status",
            type=openapi.TYPE_STRING,
            enum=['pending', 'verified', 'rejected']
        ),
    ],
    responses={
        200: openapi.Response(
            description="List of pharmacy applications",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'results': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_STRING),
                                'name': openapi.Schema(type=openapi.TYPE_STRING),
                                'owner_name': openapi.Schema(type=openapi.TYPE_STRING),
                                'owner_email': openapi.Schema(type=openapi.TYPE_STRING),
                                'address': openapi.Schema(type=openapi.TYPE_STRING),
                                'phone': openapi.Schema(type=openapi.TYPE_STRING),
                                'license_number': openapi.Schema(type=openapi.TYPE_STRING),
                                'verified': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                'created_at': openapi.Schema(type=openapi.TYPE_STRING, format='datetime'),
                                'certificate_of_operation': openapi.Schema(type=openapi.TYPE_STRING),
                            }
                        )
                    ),
                }
            )
        ),
        403: "Forbidden - Admin access required",
    },
    tags=['Admin Management']
)
@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def pending_pharmacy_applications(request):
    """Get pending pharmacy applications (Admin only)"""
    status_filter = request.query_params.get('status', 'pending')

    if status_filter == 'pending':
        pharmacies = Pharmacy.objects.filter(verified=False)
    elif status_filter == 'verified':
        pharmacies = Pharmacy.objects.filter(verified=True)
    elif status_filter == 'rejected':
        pharmacies = Pharmacy.objects.filter(verified=False)
    else:
        pharmacies = Pharmacy.objects.all()

    pharmacies = pharmacies.select_related('owner').order_by('-created_at')

    results = []
    for pharmacy in pharmacies:
        results.append({
            'id': str(pharmacy.id),
            'name': pharmacy.name,
            'owner_name': pharmacy.owner.get_full_name() or pharmacy.owner.username,
            'owner_email': pharmacy.owner.email,
            'address': pharmacy.address,
            'phone': str(pharmacy.phone) if pharmacy.phone else '',
            'license_number': pharmacy.license_number,
            'verified': pharmacy.verified,
            'created_at': pharmacy.created_at,
            'certificate_of_operation': pharmacy.certificate_of_operation.url if pharmacy.certificate_of_operation else None,
        })

    return Response({
        'count': len(results),
        'results': results
    })