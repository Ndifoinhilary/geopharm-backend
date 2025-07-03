import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from base.models import Profile
from pharm.models import (
    DrugCategory, Drug, Pharmacy, PharmacyRating, SavedPharmacy,
    PharmacyVisit, Inventory, InventoryAlert, PriceHistory, SearchHistory
)

User = get_user_model()


class Command(BaseCommand):
    help = 'Generate mock data for the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before generating new data',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            self.clear_data()

        self.stdout.write('Generating mock data...')

        try:
            with transaction.atomic():
                users = self.create_users()
                profiles = self.create_profiles(users)
                categories = self.create_drug_categories()
                drugs = self.create_drugs(categories)
                pharmacies = self.create_pharmacies(users)
                inventories = self.create_inventories(pharmacies, drugs)
                self.create_pharmacy_ratings(users, pharmacies)
                self.create_saved_pharmacies(users, pharmacies)
                self.create_pharmacy_visits(users, pharmacies)
                self.create_inventory_alerts(inventories)
                self.create_price_history(inventories, users)
                self.create_search_history(users)

            self.stdout.write(
                self.style.SUCCESS('Successfully generated mock data!')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error generating mock data: {e}')
            )
            raise

    def clear_data(self):
        """Clear existing data from all models"""
        try:
            with transaction.atomic():
                SearchHistory.objects.all().delete()
                PriceHistory.objects.all().delete()
                InventoryAlert.objects.all().delete()
                Inventory.objects.all().delete()
                PharmacyVisit.objects.all().delete()
                SavedPharmacy.objects.all().delete()
                PharmacyRating.objects.all().delete()
                Pharmacy.objects.all().delete()
                Drug.objects.all().delete()
                DrugCategory.objects.all().delete()
                Profile.objects.all().delete()
                User.objects.filter(is_superuser=False).delete()

            self.stdout.write('Data cleared successfully!')
        except Exception as e:
            self.stdout.write(f'Error clearing data: {e}')
            raise

    def create_users(self):
        """Create sample users"""
        users = []

        # Sample user data
        user_data = [
            {
                'email': 'john.patient@example.com',
                'username': 'john_patient',
                'first_name': 'John',
                'last_name': 'Doe',
                'is_patient': True,
                'is_verified': True,
                'is_active': True
            },
            {
                'email': 'jane.patient@example.com',
                'username': 'jane_patient',
                'first_name': 'Jane',
                'last_name': 'Smith',
                'is_patient': True,
                'is_verified': True,
                'is_active': True
            },
            {
                'email': 'mike.pharmacy@example.com',
                'username': 'mike_pharmacy',
                'first_name': 'Mike',
                'last_name': 'Johnson',
                'is_pharmacy_owner': True,
                'is_verified': True,
                'is_active': True
            },
            {
                'email': 'sarah.pharmacy@example.com',
                'username': 'sarah_pharmacy',
                'first_name': 'Sarah',
                'last_name': 'Wilson',
                'is_pharmacy_owner': True,
                'is_verified': True,
                'is_active': True
            },
            {
                'email': 'admin@example.com',
                'username': 'admin',
                'first_name': 'Admin',
                'last_name': 'User',
                'is_staff': True,
                'is_superuser': True,
                'is_verified': True,
                'is_active': True
            }
        ]

        # Create additional random users
        for i in range(10):
            user_data.append({
                'email': f'user{i}@example.com',
                'username': f'user_{i}',
                'first_name': f'User{i}',
                'last_name': f'LastName{i}',
                'is_patient': random.choice([True, False]),
                'is_pharmacy_owner': random.choice([True, False]),
                'is_verified': True,
                'is_active': True
            })

        for data in user_data:
            try:
                # Check if a user already exists
                if User.objects.filter(email=data['email']).exists():
                    self.stdout.write(f'User {data["email"]} already exists, skipping...')
                    continue

                user = User.objects.create_user(
                    email=data['email'],
                    username=data['username'],
                    password='testpass123',
                    first_name=data['first_name'],
                    last_name=data['last_name'],
                    is_patient=data.get('is_patient', False),
                    is_pharmacy_owner=data.get('is_pharmacy_owner', False),
                    is_staff=data.get('is_staff', False),
                    is_verified=data.get('is_verified', True),
                    is_active=data.get('is_active', True)
                )
                if data.get('is_superuser'):
                    user.is_superuser = True
                    user.save()
                users.append(user)
            except Exception as e:
                self.stdout.write(f'Error creating user {data["email"]}: {e}')

        self.stdout.write(f'Created {len(users)} users')
        return users

    def create_profiles(self, users):
        """Create profiles for users"""
        profiles = []
        cities = ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia']
        locations = ['USA', 'Canada', 'UK', 'Australia']

        for user in users:
            try:
                # Check if a profile already exists
                if hasattr(user, 'profile') and user.profile:
                    self.stdout.write(f'Profile for user {user.email} already exists, skipping...')
                    continue

                # Create a profile with only the fields that exist in your model
                profile_data = {
                    'id': uuid.uuid4(),  # Explicitly set UUID
                    'user': user,
                    'bio': f'This is the bio for {user.first_name} {user.last_name}. '
                           f'Lorem ipsum dolor sit amet, consectetur adipiscing elit.',
                    'location': random.choice(locations),
                    'city': random.choice(cities)
                }

                profile, created = Profile.objects.get_or_create(
                    user=user,
                    defaults=profile_data
                )

                if created:
                    profiles.append(profile)
                    self.stdout.write(f'Created profile for {user.email}')
                else:
                    self.stdout.write(f'Profile for {user.email} already existed')

            except Exception as e:
                self.stdout.write(f'Error creating profile for user {user.email}: {e}')

        self.stdout.write(f'Created {len(profiles)} new profiles')
        return profiles

    def create_drug_categories(self):
        """Create drug categories"""
        categories_data = [
            {
                'name': 'Pain Relief',
                'description': 'Medications for pain management and relief'
            },
            {
                'name': 'Antibiotics',
                'description': 'Medications to treat bacterial infections'
            },
            {
                'name': 'Cardiovascular',
                'description': 'Medications for heart and blood vessel conditions'
            },
            {
                'name': 'Diabetes',
                'description': 'Medications for diabetes management'
            },
            {
                'name': 'Respiratory',
                'description': 'Medications for respiratory conditions'
            },
            {
                'name': 'Mental Health',
                'description': 'Medications for mental health conditions'
            },
            {
                'name': 'Vitamins & Supplements',
                'description': 'Nutritional supplements and vitamins'
            },
            {
                'name': 'Skin Care',
                'description': 'Topical medications and skin treatments'
            }
        ]

        categories = []
        for data in categories_data:
            try:
                category, created = DrugCategory.objects.get_or_create(
                    name=data['name'],
                    defaults={
                        'id': uuid.uuid4(),
                        'description': data['description']
                    }
                )
                categories.append(category)
            except Exception as e:
                self.stdout.write(f'Error creating category {data["name"]}: {e}')

        self.stdout.write(f'Created {len(categories)} drug categories')
        return categories

    def create_drugs(self, categories):
        """Create drugs"""
        if not categories:
            self.stdout.write('No categories available, skipping drug creation')
            return []

        drugs_data = [
            # Pain Relief
            {
                'name': 'Ibuprofen',
                'category': categories[0],
                'generic_name': 'Ibuprofen',
                'manufacturer': 'Generic Pharma',
                'dosage': '200mg',
                'drug_form': 'Tablet',
                'side_effects': 'Stomach upset, dizziness, headache',
                'requires_prescription': False
            },
            {
                'name': 'Acetaminophen',
                'category': categories[0],
                'generic_name': 'Paracetamol',
                'manufacturer': 'MediCorp',
                'dosage': '500mg',
                'drug_form': 'Tablet',
                'side_effects': 'Liver damage (with overdose)',
                'requires_prescription': False
            },
            # Antibiotics
            {
                'name': 'Amoxicillin',
                'category': categories[1] if len(categories) > 1 else categories[0],
                'generic_name': 'Amoxicillin',
                'manufacturer': 'BioPharm',
                'dosage': '250mg',
                'drug_form': 'Capsule',
                'side_effects': 'Nausea, diarrhea, allergic reactions',
                'requires_prescription': True
            },
            {
                'name': 'Azithromycin',
                'category': categories[1] if len(categories) > 1 else categories[0],
                'generic_name': 'Azithromycin',
                'manufacturer': 'HealthCorp',
                'dosage': '500mg',
                'drug_form': 'Tablet',
                'side_effects': 'Stomach pain, diarrhea, nausea',
                'requires_prescription': True
            },
            # Vitamins
            {
                'name': 'Vitamin D3',
                'category': categories[6] if len(categories) > 6 else categories[0],
                'generic_name': 'Cholecalciferol',
                'manufacturer': 'VitaHealth',
                'dosage': '1000 IU',
                'drug_form': 'Capsule',
                'side_effects': 'Rare: hypercalcemia',
                'requires_prescription': False
            }
        ]

        drugs = []
        for data in drugs_data:
            try:
                drug, created = Drug.objects.get_or_create(
                    name=data['name'],
                    dosage=data['dosage'],
                    defaults={
                        'id': uuid.uuid4(),  # Explicitly set UUID
                        **{k: v for k, v in data.items() if k not in ['name', 'dosage']}
                    }
                )
                drugs.append(drug)
            except Exception as e:
                self.stdout.write(f'Error creating drug {data["name"]}: {e}')

        drug_names = ['Aspirin', 'Cetirizine', 'Omeprazole', 'Simvastatin', 'Losartan']
        for i, name in enumerate(drug_names):
            try:
                dosage = f'{random.randint(10, 500)}mg'
                drug, created = Drug.objects.get_or_create(
                    name=name,
                    dosage=dosage,
                    defaults={
                        'id': uuid.uuid4(),  # Explicitly set UUID
                        'category': random.choice(categories),
                        'generic_name': name,
                        'manufacturer': f'Manufacturer {i}',
                        'drug_form': random.choice(['Tablet', 'Capsule', 'Syrup', 'Injection']),
                        'side_effects': 'Common side effects may include...',
                        'requires_prescription': random.choice([True, False])
                    }
                )
                drugs.append(drug)
            except Exception as e:
                self.stdout.write(f'Error creating drug {name}: {e}')

        self.stdout.write(f'Created {len(drugs)} drugs')
        return drugs

    def create_pharmacies(self, users):
        """Create pharmacies"""
        pharmacy_owners = [user for user in users if user.is_pharmacy_owner]

        if not pharmacy_owners:
            self.stdout.write('No pharmacy owners available, skipping pharmacy creation')
            return []

        pharmacies_data = [
            {
                'name': 'City Central Pharmacy',
                'address': '123 Main Street, Downtown',
                'city': 'New York',
                'latitude': Decimal('40.7128'),
                'longitude': Decimal('-74.0060'),
                'phone': '+1234567890',
                'email': 'info@citycentral.com',
                'opening_hours': '8 AM - 10 PM',
                'verified': True,
                'is_24_hours': False,
                'license_number': 'PHM-NYC-001'
            },
            {
                'name': '24/7 Health Pharmacy',
                'address': '456 Health Avenue',
                'city': 'Los Angeles',
                'latitude': Decimal('34.0522'),
                'longitude': Decimal('-118.2437'),
                'phone': '+1987654321',
                'email': 'contact@24health.com',
                'opening_hours': '24 Hours',
                'verified': True,
                'is_24_hours': True,
                'license_number': 'PHM-LA-002'
            },
            {
                'name': 'Community Care Pharmacy',
                'address': '789 Community Road',
                'city': 'Chicago',
                'latitude': Decimal('41.8781'),
                'longitude': Decimal('-87.6298'),
                'phone': '+1122334455',
                'email': 'help@communitycare.com',
                'opening_hours': '7 AM - 9 PM',
                'verified': False,
                'is_24_hours': False,
                'license_number': 'PHM-CHI-003'
            }
        ]

        pharmacies = []
        for i, data in enumerate(pharmacies_data):
            if i < len(pharmacy_owners):
                try:
                    pharmacy, created = Pharmacy.objects.get_or_create(
                        owner=pharmacy_owners[i],
                        defaults={
                            'id': uuid.uuid4(),  # Explicitly set UUID
                            **data,
                            'established_date': timezone.now().date() - timedelta(days=random.randint(100, 3650)),
                            'description': f'A trusted pharmacy serving the community for years.'
                        }
                    )
                    pharmacies.append(pharmacy)
                except Exception as e:
                    self.stdout.write(f'Error creating pharmacy {data["name"]}: {e}')

        self.stdout.write(f'Created {len(pharmacies)} pharmacies')
        return pharmacies

    def create_inventories(self, pharmacies, drugs):
        """Create inventory items"""
        if not pharmacies or not drugs:
            self.stdout.write('No pharmacies or drugs available, skipping inventory creation')
            return []

        inventories = []

        for pharmacy in pharmacies:
            # Add random drugs to each pharmacy's inventory
            selected_drugs = random.sample(drugs, min(len(drugs), random.randint(3, 8)))

            for drug in selected_drugs:
                try:
                    inventory, created = Inventory.objects.get_or_create(
                        pharmacy=pharmacy,
                        drug=drug,
                        defaults={
                            'id': uuid.uuid4(),  # Explicitly set UUID
                            'quantity': random.randint(0, 100),
                            'price': Decimal(str(random.uniform(5.0, 200.0))),
                            'cost_price': Decimal(str(random.uniform(2.0, 150.0))),
                            'low_stock_threshold': random.randint(5, 15),
                            'expiry_date': timezone.now().date() + timedelta(days=random.randint(30, 730)),
                            'batch_number': f'BATCH-{random.randint(1000, 9999)}',
                            'supplier': f'Supplier {random.randint(1, 10)}',
                            'notes': 'Quality checked and stored properly'
                        }
                    )
                    if created:
                        inventories.append(inventory)
                except Exception as e:
                    self.stdout.write(f'Error creating inventory for {drug.name} at {pharmacy.name}: {e}')

        self.stdout.write(f'Created {len(inventories)} inventory items')
        return inventories

    def create_pharmacy_ratings(self, users, pharmacies):
        """Create pharmacy ratings"""
        if not users or not pharmacies:
            return []

        patients = [user for user in users if user.is_patient]
        if not patients:
            patients = users  # Use all users if no patients

        ratings = []

        for _ in range(20):
            try:
                user = random.choice(patients)
                pharmacy = random.choice(pharmacies)

                # Avoid duplicate ratings
                rating, created = PharmacyRating.objects.get_or_create(
                    user=user,
                    pharmacy=pharmacy,
                    defaults={
                        'id': uuid.uuid4(),  # Explicitly set UUID
                        'rating': random.randint(1, 5),
                        'review': f'Great service! Highly recommend this pharmacy.'
                    }
                )
                if created:
                    ratings.append(rating)
            except Exception as e:
                self.stdout.write(f'Error creating rating: {e}')

        self.stdout.write(f'Created {len(ratings)} pharmacy ratings')
        return ratings

    def create_saved_pharmacies(self, users, pharmacies):
        """Create saved pharmacies"""
        if not users or not pharmacies:
            return []

        patients = [user for user in users if user.is_patient]
        if not patients:
            patients = users

        saved = []

        for _ in range(15):
            try:
                user = random.choice(patients)
                pharmacy = random.choice(pharmacies)

                saved_pharmacy, created = SavedPharmacy.objects.get_or_create(
                    user=user,
                    pharmacy=pharmacy,
                    defaults={
                        'id': uuid.uuid4()  # Explicitly set UUID
                    }
                )
                if created:
                    saved.append(saved_pharmacy)
            except Exception as e:
                self.stdout.write(f'Error creating saved pharmacy: {e}')

        self.stdout.write(f'Created {len(saved)} saved pharmacies')
        return saved

    def create_pharmacy_visits(self, users, pharmacies):
        """Create pharmacy visits"""
        if not users or not pharmacies:
            return []

        patients = [user for user in users if user.is_patient]
        if not patients:
            patients = users

        visits = []

        for _ in range(30):
            try:
                visit = PharmacyVisit.objects.create(
                    id=uuid.uuid4(),  # Explicitly set UUID
                    user=random.choice(patients),
                    pharmacy=random.choice(pharmacies)
                )
                visits.append(visit)
            except Exception as e:
                self.stdout.write(f'Error creating visit: {e}')

        self.stdout.write(f'Created {len(visits)} pharmacy visits')
        return visits

    def create_inventory_alerts(self, inventories):
        """Create inventory alerts"""
        if not inventories:
            return []

        alerts = []
        alert_types = ['low_stock', 'out_of_stock', 'expiring_soon', 'expired']

        for _ in range(10):
            try:
                inventory = random.choice(inventories)
                alert_type = random.choice(alert_types)

                alert = InventoryAlert.objects.create(
                    id=uuid.uuid4(),  # Explicitly set UUID
                    inventory=inventory,
                    alert_type=alert_type,
                    message=f'Alert: {inventory.drug.name} in {inventory.pharmacy.name} - {alert_type.replace("_", " ").title()}',
                    is_resolved=random.choice([True, False])
                )
                alerts.append(alert)
            except Exception as e:
                self.stdout.write(f'Error creating alert: {e}')

        self.stdout.write(f'Created {len(alerts)} inventory alerts')
        return alerts

    def create_price_history(self, inventories, users):
        """Create price history"""
        if not inventories:
            return []

        pharmacy_owners = [user for user in users if user.is_pharmacy_owner]
        price_histories = []

        for _ in range(15):
            try:
                inventory = random.choice(inventories)
                old_price = inventory.price
                new_price = Decimal(str(random.uniform(5.0, 200.0)))

                price_history = PriceHistory.objects.create(
                    id=uuid.uuid4(),  # Explicitly set UUID
                    inventory=inventory,
                    old_price=old_price,
                    new_price=new_price,
                    changed_by=random.choice(pharmacy_owners) if pharmacy_owners else None,
                    reason=random.choice(['Market price change', 'Supplier cost update', 'Promotional pricing'])
                )
                price_histories.append(price_history)
            except Exception as e:
                self.stdout.write(f'Error creating price history: {e}')

        self.stdout.write(f'Created {len(price_histories)} price history records')
        return price_histories

    def create_search_history(self, users):
        """Create search history"""
        if not users:
            return []

        patients = [user for user in users if user.is_patient]
        if not patients:
            patients = users

        search_queries = [
            'Ibuprofen', 'Paracetamol', 'Vitamin D', 'Blood pressure medication',
            'Diabetes medicine', 'Antibiotics', 'Pain relief', 'Cough syrup',
            'Allergy medication', 'Antacid'
        ]

        searches = []
        for _ in range(25):
            try:
                search = SearchHistory.objects.create(
                    user=random.choice(patients),
                    query=random.choice(search_queries)
                )
                searches.append(search)
            except Exception as e:
                self.stdout.write(f'Error creating search history: {e}')

        self.stdout.write(f'Created {len(searches)} search history records')
        return searches


# passwords = testpass123
