"""
Tests for the quicklinks app.

This module provides test cases for:
- QuickLink model
- QuickLink API endpoints
- Icon upload/download
- Permissions
"""

import io
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from PIL import Image

from .models import QuickLink

User = get_user_model()


class QuickLinkModelTests(TestCase):
    """Test cases for the QuickLink model"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            password='testpass123',
            role='admin'
        )
    
    def test_create_quicklink(self):
        """Test creating a quick link"""
        quicklink = QuickLink.objects.create(
            name='Test Link',
            redirect_url='https://example.com',
            created_by=self.user
        )
        
        self.assertEqual(quicklink.name, 'Test Link')
        self.assertEqual(quicklink.redirect_url, 'https://example.com')
        self.assertTrue(quicklink.is_active)
        self.assertEqual(quicklink.position, 0)
    
    def test_auto_position_assignment(self):
        """Test automatic position assignment for new quick links"""
        link1 = QuickLink.objects.create(
            name='Link 1',
            redirect_url='https://example1.com',
            created_by=self.user
        )
        link2 = QuickLink.objects.create(
            name='Link 2',
            redirect_url='https://example2.com',
            created_by=self.user
        )
        
        # Refresh from database
        link2.refresh_from_db()
        
        # Second link should have position 1
        self.assertEqual(link2.position, 1)
    
    def test_has_icon_property(self):
        """Test has_icon property"""
        quicklink = QuickLink.objects.create(
            name='Test Link',
            redirect_url='https://example.com',
            created_by=self.user
        )
        
        self.assertFalse(quicklink.has_icon)
        
        # Add icon data
        quicklink.icon_data = b'fake_icon_data'
        quicklink.save()
        
        self.assertTrue(quicklink.has_icon)
    
    def test_clear_icon(self):
        """Test clearing icon from quick link"""
        quicklink = QuickLink.objects.create(
            name='Test Link',
            redirect_url='https://example.com',
            icon_data=b'fake_icon_data',
            icon_mime_type='image/png',
            icon_original_filename='test.png',
            created_by=self.user
        )
        
        self.assertTrue(quicklink.has_icon)
        
        quicklink.clear_icon()
        
        self.assertFalse(quicklink.has_icon)
        self.assertIsNone(quicklink.icon_data)
        self.assertIsNone(quicklink.icon_mime_type)
        self.assertIsNone(quicklink.icon_original_filename)
    
    def test_quicklink_ordering(self):
        """Test that quick links are ordered by position"""
        link3 = QuickLink.objects.create(
            name='Link 3',
            redirect_url='https://example3.com',
            position=2,
            created_by=self.user
        )
        link1 = QuickLink.objects.create(
            name='Link 1',
            redirect_url='https://example1.com',
            position=0,
            created_by=self.user
        )
        link2 = QuickLink.objects.create(
            name='Link 2',
            redirect_url='https://example2.com',
            position=1,
            created_by=self.user
        )
        
        links = list(QuickLink.objects.all())
        
        self.assertEqual(links[0].name, 'Link 1')
        self.assertEqual(links[1].name, 'Link 2')
        self.assertEqual(links[2].name, 'Link 3')


class QuickLinkAPITests(APITestCase):
    """Test cases for QuickLink API endpoints"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.admin_user = User.objects.create_user(
            username='admin@example.com',
            email='admin@example.com',
            password='adminpass123',
            role='admin'
        )
        self.regular_user = User.objects.create_user(
            username='user@example.com',
            email='user@example.com',
            password='userpass123',
            role='user'
        )
        
        self.quicklink = QuickLink.objects.create(
            name='Test Link',
            redirect_url='https://example.com',
            position=0,
            is_active=True,
            created_by=self.admin_user
        )
    
    def _create_test_image(self):
        """Create a test image file"""
        file = io.BytesIO()
        image = Image.new('RGB', (100, 100), color='red')
        image.save(file, 'PNG')
        file.name = 'test.png'
        file.seek(0)
        return file
    
    def test_list_quicklinks_authenticated(self):
        """Test listing quick links as authenticated user"""
        self.client.force_authenticate(user=self.regular_user)
        
        url = reverse('quicklink-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertIn('data', response.data)
    
    def test_list_quicklinks_unauthenticated(self):
        """Test listing quick links without authentication"""
        url = reverse('quicklink-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_get_single_quicklink(self):
        """Test getting a single quick link"""
        self.client.force_authenticate(user=self.regular_user)
        
        url = reverse('quicklink-detail', kwargs={'pk': self.quicklink.pk})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['name'], 'Test Link')
    
    def test_create_quicklink_admin(self):
        """Test creating a quick link as admin"""
        self.client.force_authenticate(user=self.admin_user)
        
        url = reverse('quicklink-list')
        data = {
            'name': 'New Link',
            'redirect_url': 'https://newsite.com',
            'is_active': True
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['name'], 'New Link')
    
    def test_create_quicklink_regular_user(self):
        """Test that regular users cannot create quick links"""
        self.client.force_authenticate(user=self.regular_user)
        
        url = reverse('quicklink-list')
        data = {
            'name': 'New Link',
            'redirect_url': 'https://newsite.com'
        }
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_update_quicklink_admin(self):
        """Test updating a quick link as admin"""
        self.client.force_authenticate(user=self.admin_user)
        
        url = reverse('quicklink-detail', kwargs={'pk': self.quicklink.pk})
        data = {
            'name': 'Updated Link'
        }
        response = self.client.patch(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['name'], 'Updated Link')
    
    def test_delete_quicklink_admin(self):
        """Test deleting a quick link as admin"""
        self.client.force_authenticate(user=self.admin_user)
        
        url = reverse('quicklink-detail', kwargs={'pk': self.quicklink.pk})
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(QuickLink.objects.filter(pk=self.quicklink.pk).exists())
    
    def test_upload_icon_admin(self):
        """Test uploading an icon as admin"""
        self.client.force_authenticate(user=self.admin_user)
        
        url = reverse('quicklink-icon', kwargs={'pk': self.quicklink.pk})
        image = self._create_test_image()
        
        response = self.client.post(url, {'icon': image}, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('icon_url', response.data['data'])
        
        # Verify icon was saved
        self.quicklink.refresh_from_db()
        self.assertTrue(self.quicklink.has_icon)
    
    def test_delete_icon_admin(self):
        """Test deleting an icon as admin"""
        # First add an icon
        self.quicklink.icon_data = b'fake_icon_data'
        self.quicklink.icon_mime_type = 'image/png'
        self.quicklink.icon_original_filename = 'test.png'
        self.quicklink.save()
        
        self.client.force_authenticate(user=self.admin_user)
        
        url = reverse('quicklink-icon', kwargs={'pk': self.quicklink.pk})
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Verify icon was deleted
        self.quicklink.refresh_from_db()
        self.assertFalse(self.quicklink.has_icon)
    
    def test_bulk_position_update(self):
        """Test bulk position update"""
        link2 = QuickLink.objects.create(
            name='Link 2',
            redirect_url='https://example2.com',
            position=1,
            created_by=self.admin_user
        )
        
        self.client.force_authenticate(user=self.admin_user)
        
        url = reverse('quicklink-positions')
        data = {
            'positions': [
                {'id': self.quicklink.pk, 'position': 1},
                {'id': link2.pk, 'position': 0}
            ]
        }
        response = self.client.patch(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify positions were updated
        self.quicklink.refresh_from_db()
        link2.refresh_from_db()
        
        self.assertEqual(self.quicklink.position, 1)
        self.assertEqual(link2.position, 0)
    
    def test_filter_by_is_active(self):
        """Test filtering quick links by is_active status"""
        # Create inactive link
        inactive_link = QuickLink.objects.create(
            name='Inactive Link',
            redirect_url='https://inactive.com',
            is_active=False,
            created_by=self.admin_user
        )
        
        self.client.force_authenticate(user=self.admin_user)
        
        # Filter for active only
        url = reverse('quicklink-list') + '?is_active=true'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only include active links
        results = response.data['data']['results']
        for link in results:
            self.assertTrue(link['is_active'])


class QuickLinkImageUtilsTests(TestCase):
    """Test cases for image utilities"""
    
    def test_validate_icon_file_png(self):
        """Test validating a PNG icon file"""
        from .image_utils import validate_icon_file
        
        # Create a test PNG image
        file = io.BytesIO()
        image = Image.new('RGB', (100, 100), color='red')
        image.save(file, 'PNG')
        file.name = 'test.png'
        file.content_type = 'image/png'
        file.seek(0)
        
        mime_type, file_size, filename = validate_icon_file(file)
        
        self.assertEqual(mime_type, 'image/png')
        self.assertGreater(file_size, 0)
        self.assertEqual(filename, 'test.png')
    
    def test_optimize_icon(self):
        """Test optimizing an icon"""
        from .image_utils import optimize_icon
        
        # Create a large test image
        file = io.BytesIO()
        image = Image.new('RGB', (512, 512), color='blue')
        image.save(file, 'PNG')
        file.seek(0)
        
        icon_data, mime_type = optimize_icon(file)
        
        self.assertIsInstance(icon_data, bytes)
        self.assertIn(mime_type, ['image/png', 'image/webp'])
        
        # Verify optimized image is smaller than 256x256
        optimized_image = Image.open(io.BytesIO(icon_data))
        self.assertLessEqual(optimized_image.width, 256)
        self.assertLessEqual(optimized_image.height, 256)
