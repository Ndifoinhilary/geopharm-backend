# GeoPharm - Pharmacy Management System

A comprehensive Django-based pharmacy management system that connects patients with nearby pharmacies and helps pharmacy owners manage their inventory, ratings, and operations.

## 🚀 Features

### For Patients
- **Find Nearby Pharmacies**: Discover pharmacies based on location
- **Drug Search**: Search for medications across multiple pharmacies
- **Compare Prices**: Compare drug prices across different pharmacies
- **Pharmacy Ratings**: Rate and review pharmacies
- **Save Favorites**: Save frequently visited pharmacies
- **Visit Tracking**: Keep track of pharmacy visits

### For Pharmacy Owners
- **Inventory Management**: Add, update, and manage drug inventory
- **Price Management**: Set and update drug prices with history tracking
- **Stock Alerts**: Get notifications for low stock and expiring drugs
- **Pharmacy Profile**: Manage pharmacy information and verification status
- **Analytics**: Track inventory performance and trends

### For Administrators
- **User Management**: Manage patients and pharmacy owners
- **Drug Categories**: Manage drug categories and classifications
- **System Monitoring**: Monitor alerts and system health

## 🛠 Tech Stack

- **Backend**: Django 4.x + Django REST Framework
- **Database**: SQLite (development) / PostgreSQL (production ready)
- **Authentication**: Django's built-in authentication system
- **API Documentation**: Swagger/OpenAPI
- **Location Services**: GeoDjango compatible
- **File Storage**: Django's file handling system

## 📋 Prerequisites

- Python 3.8+
- pip (Python package manager)
- Git

## 🔧 Installation & Setup

### 1. Clone the Repository
```bash
git clone git@github.com:Ndifoinhilary/geopharm-backend.git
cd geopharm
```

### 2. Create Virtual Environment
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate

# On macOS/Linux:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file in the project root:
```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (for production)
# DATABASE_URL=postgresql://user:password@localhost:5432/geopharm

# Security Settings
MAX_LOGIN_ATTEMPTS=5
LOCK_UNTIL=300  # seconds

# File Upload Settings
MAX_FILE_SIZE=5242880  # 5MB in bytes
```

### 5. Database Setup
```bash
# Create and apply migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser account
python manage.py createsuperuser
```

### 6. Generate Mock Data (Optional)
```bash
# Generate sample data for development
python manage.py generate_mock_data --clear
```

### 7. Run the Development Server
```bash
python manage.py runserver
```

The application will be available at: `http://localhost:8000`

## 🎯 Quick Start Guide

### 1. Access the Application
- **Admin Panel**: http://localhost:8000/admin/
- **API Documentation**: http://localhost:8000/swagger/
- **API Root**: http://localhost:8000/api/

### 2. Login Credentials (After Mock Data Generation)
```
Admin User:
- Email: admin@example.com
- Password: testpass123

Patient Users:
- Email: john.patient@example.com
- Password: testpass123

Pharmacy Owner Users:
- Email: mike.pharmacy@example.com
- Password: testpass123
```

### 3. API Authentication
Most API endpoints require authentication. Use Django's session authentication or token authentication:

```bash
# Login to get session cookie
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "testpass123"}'
```

## 📁 Project Structure

```
geopharm/
├── geopharm/                 # Main project settings
│   ├── __init__.py
│   ├── settings.py          # Django settings
│   ├── urls.py              # Main URL configuration
│   └── wsgi.py              # WSGI configuration
├── base/                    # Base app (User, Profile)
│   ├── models.py            # User and Profile models
│   ├── views.py             # User-related views
│   ├── serializers.py       # User serializers
│   └── management/
│       └── commands/
│           └── generate_mock_data.py  # Mock data generator
├── pharm/                   # Pharmacy app (Main business logic)
│   ├── models.py            # Pharmacy, Drug, Inventory models
│   ├── views.py             # API viewsets
│   ├── serializers.py       # API serializers
│   ├── permissions.py       # Custom permissions
│   └── utils.py             # Utility functions
├── static/                  # Static files
├── media/                   # User uploaded files
├── requirements.txt         # Python dependencies
├── manage.py               # Django management script
└── README.md               # This file
```

## 🔌 API Endpoints

### Authentication
- `POST /api/auth/login/` - User login
- `POST /api/auth/logout/` - User logout
- `POST /api/auth/register/` - User registration

### User Management
- `GET /api/users/profile/` - Get user profile
- `PUT /api/users/profile/` - Update user profile

### Pharmacy Management
- `GET /api/pharmacies/` - List pharmacies
- `POST /api/pharmacies/` - Create pharmacy (pharmacy owners)
- `GET /api/pharmacies/{id}/` - Get pharmacy details
- `PUT /api/pharmacies/{id}/` - Update pharmacy

### Inventory Management
- `GET /api/inventory/` - List inventory items
- `POST /api/inventory/` - Add inventory item
- `PUT /api/inventory/{id}/` - Update inventory item
- `DELETE /api/inventory/{id}/` - Delete inventory item
- `GET /api/inventory/low_stock/` - Get low stock items
- `GET /api/inventory/expiring_soon/` - Get expiring items

### Drug Management
- `GET /api/drugs/` - List drugs
- `GET /api/drug-categories/` - List drug categories

For complete API documentation, visit: http://localhost:8000/swagger/

## 🗃 Database Models

### Core Models
- **User**: Extended Django user with pharmacy/patient roles
- **Profile**: User profile with additional information
- **DrugCategory**: Categories for organizing drugs
- **Drug**: Pharmaceutical drug information
- **Pharmacy**: Pharmacy information and location
- **Inventory**: Drug inventory for each pharmacy

### Relationship Models
- **PharmacyRating**: User ratings for pharmacies
- **SavedPharmacy**: User's saved/favorite pharmacies
- **PharmacyVisit**: Track user visits to pharmacies
- **InventoryAlert**: Notifications for inventory issues
- **PriceHistory**: Track price changes over time
- **SearchHistory**: User search patterns

## 🔧 Management Commands

### Generate Mock Data
```bash
# Generate sample data
python manage.py generate_mock_data

# Clear existing data and generate fresh data
python manage.py generate_mock_data --clear

# Verbose output
python manage.py generate_mock_data --verbosity=2
```

### Other Useful Commands
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Collect static files (for production)
python manage.py collectstatic

# Create superuser
python manage.py createsuperuser

# Run tests
python manage.py test
```

## 🐛 Common Issues & Troubleshooting

### 1. Database Issues
```bash
# Reset database (development only)
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
python manage.py generate_mock_data
```

### 2. Migration Issues
```bash
# Reset migrations (development only)
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete
python manage.py makemigrations
python manage.py migrate
```

### 3. Permission Errors
```bash
# Fix file permissions (Unix/Linux/macOS)
chmod +x manage.py
```

### 4. Virtual Environment Issues
```bash
# Deactivate and reactivate virtual environment
deactivate
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Reinstall dependencies
pip install -r requirements.txt
```

### 5. Mock Data Generation Errors
- Ensure all migrations are applied: `python manage.py migrate`
- Check for missing UUID defaults in BaseModel
- Verify app imports in the management command

## 🧪 Testing

Run the test suite:
```bash
# Run all tests
python manage.py test

# Run tests for specific app
python manage.py test base
python manage.py test pharm

# Run with coverage (if installed)
coverage run --source='.' manage.py test
coverage report
```

## 🚀 Deployment

### Production Checklist
1. Set `DEBUG=False` in settings
2. Configure production database (PostgreSQL recommended)
3. Set up static file serving
4. Configure email backend
5. Set up proper logging
6. Use environment variables for sensitive data
7. Set up SSL/HTTPS
8. Configure allowed hosts

### Environment Variables for Production
```env
DEBUG=False
SECRET_KEY=your-production-secret-key
DATABASE_URL=postgresql://user:password@host:port/database
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

## 📚 Development

### Adding New Features
1. Create feature branch: `git checkout -b feature/new-feature`
2. Write tests for new functionality
3. Implement the feature
4. Update documentation
5. Submit pull request

### Code Style
- Follow PEP 8 guidelines
- Use meaningful variable and function names
- Add docstrings to classes and functions
- Keep functions small and focused

### Database Changes
1. Create migrations: `python manage.py makemigrations`
2. Review migration files
3. Test migrations: `python manage.py migrate`
4. Update mock data generator if needed

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write/update tests
5. Update documentation
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👥 Support

For support and questions:
- Open an issue on GitHub
- Check the troubleshooting section above
- Review the API documentation at `/swagger/`

## 🔄 Version History

- **v1.0.0** - Initial release with core functionality
  - User management and authentication
  - Pharmacy and inventory management
  - Basic API endpoints
  - Mock data generation

---

**Happy coding! 🎉**