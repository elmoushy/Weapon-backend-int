"""
Script to create a superadmin user for WeaponPowerCloud Backend.
Usage: python create_admin_user.py
"""
import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weaponpowercloud_backend.settings')
django.setup()

from authentication.models import User

def create_superadmin():
    """Create a superadmin user with email admin@whso.com"""
    email = "admin@whso.com"
    password = "Password778811"
    
    # Check if user already exists
    if User.objects.filter_by_email(email).exists():
        print(f"❌ User with email '{email}' already exists!")
        user = User.objects.get_by_email(email)
        print(f"   Current role: {user.role}")
        print(f"   Auth type: {user.auth_type}")
        
        # Ask if user wants to update the password
        update = input("\nDo you want to update the password and role? (yes/no): ").strip().lower()
        if update == 'yes':
            user.set_password(password)
            user.role = 'super_admin'  # Role controls is_staff and is_superuser
            user.save()
            print(f"✅ User '{email}' updated successfully!")
            print(f"   Role: {user.role}")
            print(f"   Is Staff: {user.is_staff}")
            print(f"   Is Superuser: {user.is_superuser}")
            print(f"   Password: Updated")
        else:
            print("Operation cancelled.")
        return
    
    try:
        # Create superadmin user
        # Note: username is set to email for regular auth users
        # is_staff and is_superuser are automatically set based on role
        user = User.objects.create_user(
            username=email,  # Use email as username for regular auth
            email=email,
            password=password,
            auth_type='regular',
            role='super_admin'  # This automatically makes is_staff=True and is_superuser=True
        )
        
        print("✅ Superadmin user created successfully!")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Role: {user.role}")
        print(f"   Auth Type: {user.auth_type}")
        print(f"   Is Staff: {user.is_staff}")
        print(f"   Is Superuser: {user.is_superuser}")
        print("\n🔐 You can now login with these credentials.")
        
    except Exception as e:
        print(f"❌ Error creating user: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("Creating Superadmin User")
    print("=" * 60)
    create_superadmin()
    print("=" * 60)
