"""
Django management command to create test users for internal chat.

Usage:
    python manage.py create_test_users
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Create test users for internal chat testing'

    def handle(self, *args, **options):
        # Test users data
        test_users = [
            {
                'email': 'alice@weaponpower.com',
                'username': 'alice@weaponpower.com',
                'password': 'Test123!@#',
                'first_name': 'Alice',
                'last_name': 'Johnson',
                'role': 'user'
            },
            {
                'email': 'bob@weaponpower.com',
                'username': 'bob@weaponpower.com',
                'password': 'Test123!@#',
                'first_name': 'Bob',
                'last_name': 'Smith',
                'role': 'user'
            },
            {
                'email': 'charlie@weaponpower.com',
                'username': 'charlie@weaponpower.com',
                'password': 'Test123!@#',
                'first_name': 'Charlie',
                'last_name': 'Brown',
                'role': 'admin'
            },
        ]

        created_count = 0
        skipped_count = 0

        for user_data in test_users:
            email = user_data['email']
            
            # Check if user already exists
            if User.objects.filter_by_email(email).exists():
                self.stdout.write(
                    self.style.WARNING(f'⚠️  User {email} already exists. Skipping...')
                )
                skipped_count += 1
                continue

            # Create user
            try:
                user = User.objects.create_user(
                    username=user_data['username'],
                    email=user_data['email'],
                    password=user_data['password'],
                    first_name=user_data['first_name'],
                    last_name=user_data['last_name'],
                    role=user_data['role']
                )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Created user: {user.email} '
                        f'({user.first_name} {user.last_name}) - Role: {user.role}'
                    )
                )
                created_count += 1
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error creating user {email}: {str(e)}')
                )

        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'✅ Created: {created_count} users'))
        if skipped_count > 0:
            self.stdout.write(self.style.WARNING(f'⚠️  Skipped: {skipped_count} users (already exist)'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        if created_count > 0:
            self.stdout.write('')
            self.stdout.write('Login credentials for all test users:')
            self.stdout.write('  Password: Test123!@#')
