# WeaponPowerCloud Backend - AI Coding Agent Instructions

## Project Overview
Django REST Framework backend supporting **dual authentication** (Azure AD SSO + email/password), survey management with **AES-256 encryption**, and **universal database compatibility** (Oracle, SQL Server, SQLite). Built for UAE timezone operations.

## ⚠️ CRITICAL: Development Environment
**Terminal**: Always use **PowerShell** syntax - this is a Windows PowerShell environment, NOT cmd or bash.
- Use semicolons (`;`) to chain commands, NOT `&&`
- Use `$env:VARIABLE_NAME="value"` for environment variables, NOT `export VARIABLE=value`
- Use backslashes (`\`) for paths or PowerShell path syntax
- **ALWAYS activate virtual environment first**: `.\.venv\Scripts\Activate.ps1; <your command>`
- Example: `.\.venv\Scripts\Activate.ps1; $env:USE_ORACLE="True"; python manage.py migrate` ✅
- Example: `USE_ORACLE=True && python manage.py migrate` ❌

## Critical Architecture Patterns

### 1. Oracle + Python 3.12 Compatibility Fix (CRITICAL)
**Challenge**: Django 5.2 + oracledb 3.3.0 + Python 3.12 has a critical compatibility bug.

**Error**: `TypeError: isinstance() arg 2 must be a type, a tuple of types, or a union`

**Solution**: Monkey-patch applied in `weaponpowercloud_backend/oracle_fix.py`
- Patches Django's `OracleParam.__init__()` before database connection
- Applied in both `settings.py` and `wsgi.py` to ensure coverage
- Automatically detects Oracle usage and skips patch for SQLite

**Key Files**:
- `weaponpowercloud_backend/oracle_fix.py` - Compatibility patch
- `weaponpowercloud_backend/settings.py` - Applies patch on import
- `weaponpowercloud_backend/wsgi.py` - Applies patch for Gunicorn
- `ORACLE_PYTHON312_FIX.md` - Complete documentation

**⚠️ NEVER remove or modify** the `apply_oracle_fixes()` calls in settings.py or wsgi.py - they're critical for production Oracle database connectivity.

**Production verification**:
```bash
# Check patch was applied
grep "Successfully patched Django Oracle backend" logs/django.log

# Test database connectivity
curl -X POST https://lightidea.org:9006/api/auth/login/
```

### 2. Universal Database Compatibility (Oracle + SQL Server + SQLite)
**Challenge**: Different databases have varying constraints on encrypted fields and indexes.
- **Oracle**: No unique constraints on encrypted fields, uses hash-based indexes
- **SQL Server**: Similar limitations with encrypted data
- **SQLite**: Full support but limited for production use

**Solution**: Hash-based indexing pattern for ALL databases to ensure portability.

```python
# ALL models with encrypted fields follow this pattern:
class MyModel(models.Model):
    sensitive_field = EncryptedCharField(max_length=255)
    sensitive_field_hash = models.CharField(max_length=64, db_index=True)  # SHA256 hash
    
    def save(self, *args, **kwargs):
        if self.sensitive_field:
            self.sensitive_field_hash = hashlib.sha256(self.sensitive_field.encode()).hexdigest()
        super().save(*args, **kwargs)
```

**Key Files**: 
- `authentication/models.py` - User model with `email_hash`, `username_hash`
- `surveys/models.py` - Survey/Question with `title_hash`, `text_hash`
- `authentication/managers.py` - Custom managers for hash-based queries

**Use database-agnostic managers** for ALL queries on encrypted fields:
```python
User.objects.get_by_email(email)  # ✅ Works on Oracle, SQL Server, SQLite
User.objects.get(email=email)  # ❌ NEVER query encrypted fields directly

Survey.objects.filter_by_title(title)  # ✅ Database-portable approach
Survey.objects.filter(title=title)  # ❌ Fails on Oracle/SQL Server
```

**Critical**: Always use hash-based managers to maintain compatibility across Oracle, SQL Server, and SQLite.

### 3. Dual Authentication System
**Three authentication layers** work in sequence:

1. **UniversalAuthentication** (REST_FRAMEWORK setting) - Try both token types
2. **DualAuthentication** - Fallback for edge cases  
3. **SessionAuthentication** - Browsable API support

**Token Detection Flow** (`authentication/dual_auth.py`):
- Check JWT header for `kid` claim → Azure AD token
- No `kid` → Regular JWT token
- Attempt appropriate auth first, fallback to other

**Azure AD specifics** (`authentication/azure_auth.py`):
- Uses `username=Object_ID` (not email) for Azure users
- JWKS keys cached for 5 minutes
- Always creates users with `auth_type='azure'` and `role='user'`

**Regular auth** (`authentication/views.py`):
- Uses `username=email` for regular users
- Returns access + refresh tokens (30min/4hr lifetimes)

### 4. Encryption Architecture
**Three custom field types** in `surveys/models.py`:
```python
EncryptedCharField  # For short strings (titles, names)
EncryptedTextField  # For long text (descriptions, answers)
```

**Global encryption instance**: `surveys/encryption.py` → `surveys_data_encryption`
- Uses Fernet (AES-256) from `cryptography` package
- Key from `SURVEYS_ENCRYPTION_KEY` or `ENCRYPTION_KEY` env var
- Auto-generates key in DEBUG mode with warning

**NEVER** query encrypted fields directly. Use hash fields or decrypt after fetching.

### 5. UAE Timezone Enforcement & Hijri Date Conversion
**Middleware**: `weaponpowercloud_backend/middleware/emirates_timezone.py`
- Forces `Asia/Dubai` timezone for ALL requests
- Activated per-request, deactivated in finally block
- Survey scheduling uses `timezone_utils.py` helpers: `ensure_uae_timezone()`, `now_uae()`

**Hijri to Gregorian Conversion** (NEW):
- API accepts Hijri dates in input: `"H1446-09-01"` or `{"year": 1446, "month": 9, "day": 1, "is_hijri": true}`
- All dates stored and returned in Gregorian calendar with UAE timezone
- Uses `hijri-converter` library for accurate conversion
- See `HIJRI_TO_GREGORIAN_CONVERSION.md` for full documentation

**Pattern for datetime operations**:
```python
from .timezone_utils import ensure_uae_timezone, now_uae, hijri_to_gregorian_date
survey.start_date = ensure_uae_timezone(survey.start_date)  # Always convert
# Or convert from Hijri:
survey.start_date = hijri_to_gregorian_date(1446, 9, 1)  # Ramadan 1, 1446
```

### 6. Survey Visibility System
**Four visibility modes** with different access patterns:
- `PRIVATE` - Creator + explicitly shared users (via `shared_with` M2M)
- `AUTH` - Any authenticated user with valid JWT
- `PUBLIC` - Anonymous access (requires `status='submitted'`)
- `GROUPS` - Shared with specific groups (via `shared_with_groups` M2M)

**Public surveys** support:
- Per-device access control (`DeviceResponse` model tracks device fingerprints)
- Email/phone-based access control (`public_contact_method` setting)
- Password-protected sharing (`PublicAccessToken` model)

**Survey status workflow**:
- `draft` → editable, not accessible via public endpoints
- `submitted` → immutable (except PRIVATE/AUTH/GROUPS), accessible via public endpoints

### 7. Security Patterns

**Brute Force Protection** (`weaponpowercloud_backend/middleware/brute_force_protection.py`):
- Rate limits tracked in cache by IP + email
- Default: 5 attempts, 15min lockout (configurable via settings)
- Clear attempts after successful login: `clear_login_attempts(email, ip)`

**Content Security Policy**: Django CSP middleware configured in `settings.py`
- Strict CSP in production, relaxed in DEBUG mode
- Allow inline styles for Django admin only

**Input Sanitization**: 
- HTML sanitization via `bleach` (configured in settings: `ALLOWED_HTML_TAGS`)
- Max upload size: 10MB default (`MAX_UPLOAD_SIZE`)

## Development Workflows

### Running Locally
```powershell
# ⚠️ ALWAYS activate virtual environment before ANY command
# Run migrations (SQLite by default)
.\.venv\Scripts\Activate.ps1; python manage.py migrate

# Create superuser (use the script)
.\.venv\Scripts\Activate.ps1; python add_super_admin_user.py

# Run development server
.\.venv\Scripts\Activate.ps1; python manage.py runserver
```

**Critical Rule**: NEVER run Python commands without first activating the virtual environment in the same command chain using `.\.venv\Scripts\Activate.ps1;`

### Database Selection (Oracle / SQL Server / SQLite)
**Environment variable**: `USE_ORACLE=True` switches to Oracle database.

```powershell
# Local development (SQLite) - Default
.\.venv\Scripts\Activate.ps1; $env:USE_ORACLE="False"; python manage.py runserver

# Production (Oracle) - PowerShell syntax
.\.venv\Scripts\Activate.ps1; $env:USE_ORACLE="True"; python manage.py migrate --fake-initial

# Testing SQL Server compatibility (if configured)
.\.venv\Scripts\Activate.ps1; $env:DATABASE_ENGINE="sqlserver"; python manage.py migrate
```

**Migration strategy**:
- **SQLite**: Standard migrations, no special handling
- **Oracle**: Use `--fake-initial` for existing tables, hash field migrations required
- **SQL Server**: Similar to Oracle, test hash-based queries carefully

**⚠️ Database Portability Rules**:
1. NEVER use database-specific SQL in ORM queries
2. Always test on SQLite first, then Oracle/SQL Server
3. Use hash fields for all encrypted data queries
4. Avoid raw SQL unless wrapped in database-agnostic helpers
5. Check `authentication/oracle_utils.py` for cross-database patterns

### Testing
Tests in `surveys/tests.py`, `authentication/tests.py` use Django TestCase/APITestCase:
```powershell
# Run all tests (PowerShell) - ALWAYS activate venv first
.\.venv\Scripts\Activate.ps1; python manage.py test

# Run specific app tests
.\.venv\Scripts\Activate.ps1; python manage.py test surveys
.\.venv\Scripts\Activate.ps1; python manage.py test authentication

# Test with different databases (ensure portability)
.\.venv\Scripts\Activate.ps1; $env:USE_ORACLE="False"; python manage.py test  # SQLite
.\.venv\Scripts\Activate.ps1; $env:USE_ORACLE="True"; python manage.py test   # Oracle (if configured)

# Run tests with coverage
.\.venv\Scripts\Activate.ps1; python -m pytest --cov=. --cov-report=html
```

**Test data setup** follows pattern:
```python
self.user = User.objects.create_user(username="test@example.com", email="test@example.com", password="test123")
self.client.force_authenticate(user=self.user)  # For API tests
```

## Common Code Patterns

### Creating Users
```python
# Regular user (email/password)
user = User.objects.create_user(
    username=email,  # Use email as username
    email=email,
    password=password,
    auth_type='regular',
    role='user'  # or 'admin', 'super_admin'
)

# Azure AD user (created automatically on first login)
# Never create manually - handled by AzureADAuthentication
```

### Survey Access Control Checks
```python
# Check if user can access survey (in views.py)
def user_can_access_survey(user, survey):
    if survey.visibility == 'PRIVATE':
        return user == survey.creator or user in survey.shared_with.all()
    elif survey.visibility == 'AUTH':
        return user.is_authenticated
    elif survey.visibility == 'GROUPS':
        return survey.shared_with_groups.filter(users=user).exists()
    elif survey.visibility == 'PUBLIC':
        return survey.status == 'submitted'  # Public requires submission
    return False
```

### Device Fingerprint Pattern (Public Surveys)
```python
# Check if device already submitted (views.py pattern)
if survey.per_device_access:
    if DeviceResponse.has_device_submitted(survey, request):
        return Response({"error": "Device has already submitted"}, status=400)
    # Create tracking record after successful response creation
    DeviceResponse.create_device_tracking(survey, request, response_obj)
```

## File Organization Guide

### Core Apps Structure
- **authentication/** - Custom User model, Azure AD auth, dual auth, groups
- **surveys/** - Survey/Question/Response models, encryption, public access
- **notifications/** - Real-time notification system (WebSocket commented out in production)
- **weaponpowercloud_backend/** - Settings, URLs, middleware, utilities

### Key Configuration Files
- **settings.py** - Database toggle, CORS, JWT, security headers, Azure AD config
- **requirements.txt** - Note: `channels`, `daphne`, `channels-redis` commented for production
- **manage.py** - Standard Django CLI (uses `weaponpowercloud_backend.settings`)

### Migrations Strategy
- **Initial migrations**: 0001_initial.py in each app
- **Oracle-specific**: Migrations like `0010_fix_oracle_per_device_access.py` handle Oracle quirks
- **Hash fields**: Added retroactively for Oracle compatibility (authentication/surveys apps)

## API Endpoint Patterns

### Authentication Endpoints (`authentication/urls.py`)
- `POST /api/auth/login/` - Regular email/password login (returns JWT)
- `POST /api/auth/azure-login/` - Azure AD SSO login (validates Azure JWT, returns app JWT)
- `POST /api/auth/refresh/` - Refresh access token
- `POST /api/auth/add-user/` - Admin endpoint to create users
- `GET /api/auth/groups/` - List user's groups

### Survey Endpoints (`surveys/urls.py`)
- `GET /api/surveys/` - List user's accessible surveys
- `POST /api/surveys/` - Create new survey (draft by default)
- `PATCH /api/surveys/{id}/submit/` - Submit survey (makes it final)
- `POST /api/surveys/{id}/responses/` - Submit response (auth required)
- `GET /api/surveys/public-access/{token}/` - Public survey access (no auth)
- `POST /api/surveys/public-access/{token}/responses/` - Submit public response
- `GET /api/surveys/{id}/analytics/` - Survey analytics (creator/shared users only)

## Environment Variables Reference

**Required for Production**:
- `SECRET_KEY` - Django secret key
- `DEBUG=False` - Disable debug mode
- `ALLOWED_HOST` - Comma-separated hostnames

**Database Configuration** (choose one):
- **Oracle**: `USE_ORACLE=True` + `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE`, `ORACLE_USERNAME`, `ORACLE_PASSWORD`
- **SQL Server**: `DATABASE_ENGINE=sqlserver` + connection string variables (if configured)
- **SQLite**: Default, no env vars needed (not recommended for production)

**Authentication**:
- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` - Azure AD configuration
- `SURVEYS_ENCRYPTION_KEY` or `ENCRYPTION_KEY` - Fernet encryption key

**Security (Production)**:
- `MAX_LOGIN_ATTEMPTS=3`, `LOCKOUT_DURATION_MINUTES=15`
- `CORS_ALLOWED_ORIGINS` - Comma-separated frontend URLs

**Optional**:
- `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True` - HTTPS enforcement
- `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS=31536000`

## Troubleshooting Guide

### Database Issues
**Oracle character set mismatch**: Set `NLS_LANG=AMERICAN_AMERICA.AL32UTF8` (handled in settings.py)

**SQL Server connection issues**: Verify `DATABASE_ENGINE` and connection string format in settings.py

**Migration conflicts**: Use `python manage.py migrate --fake-initial` for Oracle/SQL Server with existing tables

**Encrypted field queries failing**: Check if using custom managers (`get_by_email()` not `get(email=)`)

**Database portability test**: Run migrations on SQLite first, then Oracle, then SQL Server to catch compatibility issues early

### PowerShell Command Errors
**"&&" not recognized**: You're in PowerShell, use `;` instead
```powershell
# Wrong (bash/cmd syntax)
export VAR=value && python manage.py migrate  # ❌

# Wrong (missing venv activation)
$env:VAR="value"; python manage.py migrate  # ❌

# Correct (PowerShell syntax with venv activation)
.\.venv\Scripts\Activate.ps1; $env:VAR="value"; python manage.py migrate  # ✅
```

**Missing virtual environment activation**: ALWAYS activate venv before running Python commands
```powershell
# Wrong - runs in wrong Python environment
python manage.py runserver  # ❌

# Correct - activates venv first
.\.venv\Scripts\Activate.ps1; python manage.py runserver  # ✅
```

**Path issues**: Use PowerShell path syntax or backslashes
```powershell
# Acceptable approaches
.\.venv\Scripts\Activate.ps1  # ✅
python .\manage.py runserver  # ✅
```

### Authentication Issues
**Azure AD login fails**: Verify `AZURE_CLIENT_ID` matches app registration, check JWKS cache expiry (5min TTL)

### Survey Issues
**Public survey 403**: Ensure survey `status='submitted'` AND `visibility='PUBLIC'`

**Device fingerprint duplicates**: Frontend must send `X-Screen-Resolution`, `X-Timezone`, `X-Platform` headers

### Hijri Date Issues
**Invalid Hijri date**: Ensure format is `H1446-09-01` or dict with `is_hijri: true`

**Wrong conversion**: Use 'H' prefix for Hijri strings, without it dates are treated as Gregorian

---

**Last Updated**: 2024-10-22 | **Django**: 5.2.4 | **DRF**: 3.16.0 | **Python**: 3.13+ | **New**: Hijri Date Support
