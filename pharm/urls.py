# urls.py - Complete Advanced URL Configuration
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views
from .views import pending_pharmacy_applications, manage_pharmacy_application

# Create a router for ViewSets
router = DefaultRouter()

# Basic ViewSets
router.register(r'drugs-discovery', views.DrugDiscoveryViewSet, basename='drugs-discovery')
router.register(r'drug-categories', views.DrugCategoryManagementViewSet, basename='drug-categories')
router.register(r'pharmacies', views.PharmacyProfileViewSet, basename='pharmacies')
router.register(r'inventory-analytics', views.InventoryAnalyticsViewSet, basename='inventory-analytics')
router.register(r'inventory-alerts', views.InventoryAlertViewSet, basename='inventory-alerts')
router.register(r'drugs', views.DrugViewSet)
router.register(r'pharmacies-application', views.PharmacyViewSet, basename='pharmacies-application')
router.register(r'inventory', views.InventoryManagementViewSet, basename='inventory')

urlpatterns = [

    # ===================== ROUTER URLS =====================
    path('', include(router.urls)),

    # ===================== PATIENT ENDPOINTS =====================
    # Dashboard & Analytics
    path('patient/dashboard/', views.user_dashboard, name='patient-dashboard'),
    path('patient/analytics/', views.patient_analytics, name='patient-analytics'),

    # Drug Search & Discovery
    path('drugs/search/', views.search_drugs, name='drug-search'),
    path('drugs/search/advanced/', views.advanced_drug_search, name='advanced-drug-search'),
    path('drugs/autocomplete/', views.drug_autocomplete, name='drug-autocomplete'),
    path('drugs/recommendations/', views.drug_recommendations, name='drug-recommendations'),

    # Pharmacy Discovery
    path('pharmacies/search/', views.pharmacy_search, name='pharmacy-search'),

    # ===================== PHARMACIST ENDPOINTS =====================
    # Dashboard & Analytics
    path('pharmacy/dashboard/', views.pharmacist_dashboard, name='pharmacy-dashboard'),
    path('pharmacy/analytics/', views.pharmacy_analytics, name='pharmacy-analytics'),

    # Inventory Management
    path('inventory/analytics/', views.InventoryAnalyticsViewSet.as_view({'get': 'dashboard_analytics'}),
         name='inventory-analytics'),
    path('inventory/bulk-price-update/',
         views.InventoryAnalyticsViewSet.as_view({'post': 'bulk_price_update'}), name='bulk-price-update'),
    path('inventory/expiry-report/', views.InventoryAnalyticsViewSet.as_view({'get': 'expiry_report'}),
         name='expiry-report'),

    # Alert Management
    path('alerts/resolve-all/', views.InventoryAlertViewSet.as_view({'post': 'resolve_all'}),
         name='resolve-all-alerts'),

    # ===================== SHARED ENDPOINTS =====================
    # Drug Information
    path('drugs/<int:pk>/pharmacies/', views.DrugDiscoveryViewSet.as_view({'get': 'pharmacies'}),
         name='drug-pharmacies'),
    path('drugs/<int:pk>/price-analysis/', views.DrugDiscoveryViewSet.as_view({'get': 'price_analysis'}),
         name='drug-price-analysis'),

    # Drug Categories
    path('drug-categories/<int:pk>/drugs/', views.DrugCategoryManagementViewSet.as_view({'get': 'drugs'}),
         name='category-drugs'),
    path('drug-categories/<int:pk>/pharmacies/', views.DrugCategoryManagementViewSet.as_view({'get': 'pharmacies'}),
         name='category-pharmacies'),

    # Pharmacy Information
    path('pharmacies/<int:pk>/rate/', views.PharmacyProfileViewSet.as_view({'post': 'rate'}),
         name='rate-pharmacy'),
    path('pharmacies/<int:pk>/reviews/', views.PharmacyProfileViewSet.as_view({'get': 'reviews'}),
         name='pharmacy-reviews'),
    path('pharmacies/<int:pk>/analytics/', views.PharmacyProfileViewSet.as_view({'get': 'analytics'}),
         name='pharmacy-public-analytics'),

    path('admin/pharmacy-applications/', pending_pharmacy_applications, name='pending-pharmacy-applications'),
    path('admin/pharmacy-applications/<uuid:pharmacy_id>/manage/', manage_pharmacy_application,
         name='manage-pharmacy-application'),
]
