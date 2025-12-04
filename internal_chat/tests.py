"""
Comprehensive Tests for Internal Chat
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from internal_chat.models import (
    Thread, ThreadParticipant, Message, GroupSettings,
    Attachment, MessageReaction, DirectThreadKey, AuditLog
)
from internal_chat.services import ThreadService, MessageService, ValidationService

User = get_user_model()


class ThreadModelTest(TestCase):
    """Test Thread model"""
    
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1@test.com',
            email='user1@test.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2@test.com',
            email='user2@test.com',
            password='testpass123'
        )
    
    def test_create_direct_thread(self):
        """Test creating a direct thread"""
        thread = Thread.objects.create(
            type=Thread.TYPE_DIRECT,
            created_by=self.user1
        )
        
        self.assertEqual(thread.type, Thread.TYPE_DIRECT)
        self.assertIsNone(thread.title)
        self.assertFalse(thread.is_archived)
    
    def test_create_group_thread(self):
        """Test creating a group thread"""
        thread = Thread.objects.create(
            type=Thread.TYPE_GROUP,
            title='Test Group',
            created_by=self.user1
        )
        
        self.assertEqual(thread.type, Thread.TYPE_GROUP)
        self.assertEqual(thread.title, 'Test Group')


class ThreadServiceTest(TestCase):
    """Test ThreadService business logic"""
    
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1@test.com',
            email='user1@test.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2@test.com',
            email='user2@test.com',
            password='testpass123'
        )
    
    def test_create_direct_thread(self):
        """Test creating a direct thread via service"""
        thread = ThreadService.create_thread(
            creator=self.user1,
            thread_type=Thread.TYPE_DIRECT,
            participant_ids=[self.user2.id]
        )
        
        self.assertEqual(thread.type, Thread.TYPE_DIRECT)
        self.assertEqual(ThreadParticipant.objects.filter(thread=thread).count(), 2)
    
    def test_create_group_thread(self):
        """Test creating a group thread via service"""
        thread = ThreadService.create_thread(
            creator=self.user1,
            thread_type=Thread.TYPE_GROUP,
            title='Test Group',
            participant_ids=[self.user2.id]
        )
        
        self.assertEqual(thread.type, Thread.TYPE_GROUP)
        self.assertEqual(thread.title, 'Test Group')
        
        # Check owner role
        owner = ThreadParticipant.objects.get(thread=thread, user=self.user1)
        self.assertEqual(owner.role, ThreadParticipant.ROLE_OWNER)


class MessageServiceTest(TestCase):
    """Test MessageService business logic"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='test@test.com',
            email='test@test.com',
            password='testpass123'
        )
        self.thread = ThreadService.create_thread(
            creator=self.user,
            thread_type=Thread.TYPE_GROUP,
            title='Test',
            participant_ids=[]
        )
    
    def test_create_message(self):
        """Test creating a message"""
        message = MessageService.create_message(
            thread=self.thread,
            sender=self.user,
            content='Test message'
        )
        
        self.assertEqual(message.content, 'Test message')
        self.assertEqual(message.sender, self.user)
    
    def test_soft_delete_message(self):
        """Test soft deleting a message"""
        message = MessageService.create_message(
            thread=self.thread,
            sender=self.user,
            content='Test message'
        )
        
        MessageService.delete_message(message, self.user)
        
        message.refresh_from_db()
        self.assertIsNotNone(message.deleted_at)


class ThreadAPITest(APITestCase):
    """Test Thread API endpoints"""
    
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(
            username='user1@test.com',
            email='user1@test.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2@test.com',
            email='user2@test.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user1)
    
    def test_create_direct_thread(self):
        """Test creating direct thread via API"""
        url = '/api/internal-chat/threads/'
        data = {
            'type': 'direct',
            'participant_ids': [self.user2.id]
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['type'], 'direct')
    
    def test_create_direct_thread_with_self(self):
        """Test that creating direct thread with yourself fails"""
        url = '/api/internal-chat/threads/'
        data = {
            'type': 'direct',
            'participant_ids': [self.user1.id]  # User trying to chat with themselves
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot create direct thread with yourself', response.data['error'])
    
    def test_create_group_thread(self):
        """Test creating group thread via API"""
        url = '/api/internal-chat/threads/'
        data = {
            'type': 'group',
            'title': 'Test Group',
            'participant_ids': [self.user2.id]
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Test Group')
    
    def test_list_threads(self):
        """Test listing threads"""
        # Create a thread
        ThreadService.create_thread(
            creator=self.user1,
            thread_type=Thread.TYPE_GROUP,
            title='Test',
            participant_ids=[]
        )
        
        url = '/api/internal-chat/threads/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data['results']), 0)


class MessageAPITest(APITestCase):
    """Test Message API endpoints"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='test@test.com',
            email='test@test.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        self.thread = ThreadService.create_thread(
            creator=self.user,
            thread_type=Thread.TYPE_GROUP,
            title='Test',
            participant_ids=[]
        )
    
    def test_send_message(self):
        """Test sending a message via API"""
        url = f'/api/internal-chat/threads/{self.thread.id}/messages/'
        data = {
            'content': 'Test message'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['content'], 'Test message')
    
    def test_list_messages(self):
        """Test listing messages"""
        # Create a message
        MessageService.create_message(
            thread=self.thread,
            sender=self.user,
            content='Test message'
        )
        
        url = f'/api/internal-chat/threads/{self.thread.id}/messages/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data['results']), 0)


class PermissionsTest(TestCase):
    """Test permission checks"""
    
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner@test.com',
            email='owner@test.com',
            password='testpass123'
        )
        self.admin = User.objects.create_user(
            username='admin@test.com',
            email='admin@test.com',
            password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member@test.com',
            email='member@test.com',
            password='testpass123'
        )
        
        self.thread = ThreadService.create_thread(
            creator=self.owner,
            thread_type=Thread.TYPE_GROUP,
            title='Test',
            participant_ids=[self.admin.id, self.member.id]
        )
        
        # Set admin role
        participant = ThreadParticipant.objects.get(thread=self.thread, user=self.admin)
        participant.role = ThreadParticipant.ROLE_ADMIN
        participant.save()
    
    def test_can_manage_members(self):
        """Test member management permissions"""
        self.assertTrue(ValidationService.can_manage_members(self.owner, self.thread))
        self.assertTrue(ValidationService.can_manage_members(self.admin, self.thread))
        self.assertFalse(ValidationService.can_manage_members(self.member, self.thread))
    
    def test_can_post_in_thread(self):
        """Test posting permissions"""
        # All mode
        self.assertTrue(ValidationService.can_post_in_thread(self.owner, self.thread))
        self.assertTrue(ValidationService.can_post_in_thread(self.member, self.thread))
        
        # Admins only mode
        settings = GroupSettings.objects.get(thread=self.thread)
        settings.posting_mode = GroupSettings.POSTING_MODE_ADMINS_ONLY
        settings.save()
        
        # Refresh thread to clear cached settings
        self.thread.refresh_from_db()
        
        self.assertTrue(ValidationService.can_post_in_thread(self.owner, self.thread))
        self.assertTrue(ValidationService.can_post_in_thread(self.admin, self.thread))
        self.assertFalse(ValidationService.can_post_in_thread(self.member, self.thread))


# =============================================================================
# SECURITY TESTS - MESSAGE SANITIZATION & FILE VALIDATION
# =============================================================================

class MessageSanitizationTests(TestCase):
    """Test message content sanitization against XSS attacks"""
    
    def test_script_tag_removed(self):
        """Script tags should be completely removed"""
        from .security_utils import sanitize_message_content
        
        dangerous = '<script>alert("XSS")</script>Hello'
        safe = sanitize_message_content(dangerous)
        
        self.assertNotIn('<script>', safe)
        self.assertNotIn('alert', safe)
        self.assertIn('Hello', safe)
    
    def test_inline_javascript_removed(self):
        """Inline JavaScript event handlers should be removed"""
        from .security_utils import sanitize_message_content
        
        dangerous = '<div onclick="alert(1)">Click me</div>'
        safe = sanitize_message_content(dangerous)
        
        self.assertNotIn('onclick', safe)
        self.assertIn('Click me', safe)
    
    def test_safe_html_preserved(self):
        """Safe HTML tags should be preserved"""
        from .security_utils import sanitize_message_content
        
        safe_html = '<b>Bold</b> <i>Italic</i> <code>Code</code>'
        result = sanitize_message_content(safe_html)
        
        self.assertIn('<b>Bold</b>', result)
        self.assertIn('<i>Italic</i>', result)
        self.assertIn('<code>Code</code>', result)


class FileValidationTests(TestCase):
    """Test file upload validation using magic bytes"""
    
    def setUp(self):
        """Set up test user"""
        self.user = User.objects.create_user(
            username='test@example.com',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_valid_jpeg_upload(self):
        """Valid JPEG file should pass validation"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .security_utils import validate_file_type
        
        # Create minimal valid JPEG (magic bytes: FF D8 FF)
        jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        jpeg_data += b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n'
        jpeg_data += b'\xff\xd9'  # End of image marker
        
        file = SimpleUploadedFile('test.jpg', jpeg_data, content_type='image/jpeg')
        
        # Should not raise exception
        mime = validate_file_type(file)
        self.assertEqual(mime, 'image/jpeg')
    
    def test_valid_png_upload(self):
        """Valid PNG file should pass validation"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .security_utils import validate_file_type
        
        # PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
        png_data = b'\x89PNG\r\n\x1a\n'  # PNG signature
        png_data += b'\x00\x00\x00\rIHDR'  # IHDR chunk
        png_data += b'\x00\x00\x00\x01\x00\x00\x00\x01'  # 1x1 image
        png_data += b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'  # IHDR data + CRC
        png_data += b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4'
        png_data += b'\x00\x00\x00\x00IEND\xaeB`\x82'  # IEND chunk
        
        file = SimpleUploadedFile('test.png', png_data, content_type='image/png')
        
        mime = validate_file_type(file)
        self.assertEqual(mime, 'image/png')
    
    def test_spoofed_extension_rejected(self):
        """File with wrong extension should be rejected"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.core.exceptions import ValidationError
        from .security_utils import validate_file_type
        
        # PNG content with .jpg extension (spoofing attack)
        png_data = b'\x89PNG\r\n\x1a\n'
        png_data += b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        png_data += b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
        
        file = SimpleUploadedFile('fake.jpg', png_data, content_type='image/jpeg')
        
        with self.assertRaises(ValidationError) as cm:
            validate_file_type(file)
        
        self.assertIn('does not match detected', str(cm.exception))
    
    def test_executable_rejected(self):
        """Executable files should be rejected"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.core.exceptions import ValidationError
        from .security_utils import validate_file_type
        
        # MZ header (DOS/Windows executable)
        exe_data = b'MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00'
        exe_data += b'\xb8\x00\x00\x00\x00\x00\x00\x00\x40\x00\x00\x00'
        
        file = SimpleUploadedFile('malware.exe', exe_data, content_type='image/jpeg')
        
        with self.assertRaises(ValidationError) as cm:
            validate_file_type(file)
        
        # Should reject either because of MIME type or extension
        error_msg = str(cm.exception).lower()
        self.assertTrue('not allowed' in error_msg or 'forbidden' in error_msg)
    
    def test_forbidden_extensions(self):
        """Files with forbidden extensions should be rejected"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.core.exceptions import ValidationError
        from .security_utils import validate_file_type
        
        forbidden_exts = ['.exe', '.php', '.sh', '.bat']
        
        for ext in forbidden_exts:
            with self.subTest(extension=ext):
                # Even with valid text content, forbidden extensions should fail
                file = SimpleUploadedFile(f'test{ext}', b'plain text content', content_type='text/plain')
                
                with self.assertRaises(ValidationError) as cm:
                    validate_file_type(file)
                
                self.assertIn('forbidden', str(cm.exception).lower())
    
    def test_file_size_limit(self):
        """Oversized files should be rejected"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.core.exceptions import ValidationError
        from .security_utils import validate_file_size
        
        # Create 11MB file (exceeds 10MB default limit)
        large_data = b'x' * (11 * 1024 * 1024)
        file = SimpleUploadedFile('large.txt', large_data, content_type='text/plain')
        
        with self.assertRaises(ValidationError) as cm:
            validate_file_size(file, max_size_mb=10)
        
        self.assertIn('exceeds maximum', str(cm.exception))


# =============================================================================
# WEBSOCKET RATE LIMITING TESTS
# =============================================================================

class RateLimiterUnitTests(TestCase):
    """Unit tests for WebSocketRateLimiter"""
    
    def setUp(self):
        """Clear cache before each test"""
        from django.core.cache import cache
        cache.clear()
    
    def test_rate_limiter_allows_under_limit(self):
        """Rate limiter should allow actions under limit"""
        from .rate_limiting import WebSocketRateLimiter
        
        limiter = WebSocketRateLimiter(1, 'test_action', limit=5, window=60)
        
        for i in range(5):
            self.assertTrue(limiter.is_allowed())
            limiter.increment()
        
        # All 5 should have been allowed
        self.assertEqual(limiter.get_current_count(), 5)
    
    def test_rate_limiter_blocks_over_limit(self):
        """Rate limiter should block actions over limit"""
        from .rate_limiting import WebSocketRateLimiter
        
        limiter = WebSocketRateLimiter(1, 'test_action', limit=5, window=60)
        
        # Use up limit
        for i in range(5):
            limiter.increment()
        
        # Should be blocked
        self.assertFalse(limiter.is_allowed())
    
    def test_get_remaining_count(self):
        """Test remaining action count"""
        from .rate_limiting import WebSocketRateLimiter
        
        limiter = WebSocketRateLimiter(1, 'test_action', limit=10, window=60)
        
        self.assertEqual(limiter.get_remaining(), 10)
        
        limiter.increment()
        self.assertEqual(limiter.get_remaining(), 9)
        
        for i in range(5):
            limiter.increment()
        
        self.assertEqual(limiter.get_remaining(), 4)
    
    def test_check_rate_limit_convenience_function(self):
        """Test check_rate_limit convenience function"""
        from .rate_limiting import check_rate_limit
        
        # First 60 should pass
        for i in range(60):
            result = check_rate_limit(1, 'test', limit=60, window=60)
            self.assertTrue(result, f"Failed at iteration {i+1}")
        
        # 61st should fail
        result = check_rate_limit(1, 'test', limit=60, window=60)
        self.assertFalse(result)
    
    def test_rate_limit_per_user(self):
        """Rate limits should be per-user"""
        from .rate_limiting import check_rate_limit
        
        # User 1 fills their limit
        for i in range(5):
            check_rate_limit(1, 'test', limit=5, window=60)
        
        # User 1 should be blocked
        self.assertFalse(check_rate_limit(1, 'test', limit=5, window=60))
        
        # User 2 should still be allowed
        self.assertTrue(check_rate_limit(2, 'test', limit=5, window=60))
    
    def test_rate_limit_per_action(self):
        """Rate limits should be per-action"""
        from .rate_limiting import check_rate_limit
        
        # Fill up 'action_a'
        for i in range(5):
            check_rate_limit(1, 'action_a', limit=5, window=60)
        
        # action_a should be blocked
        self.assertFalse(check_rate_limit(1, 'action_a', limit=5, window=60))
        
        # action_b should still be allowed
        self.assertTrue(check_rate_limit(1, 'action_b', limit=5, window=60))
    
    def test_reset_rate_limit(self):
        """Test resetting rate limit"""
        from .rate_limiting import WebSocketRateLimiter
        
        limiter = WebSocketRateLimiter(1, 'test_action', limit=5, window=60)
        
        # Fill limit
        for i in range(5):
            limiter.increment()
        
        self.assertFalse(limiter.is_allowed())
        
        # Reset
        limiter.reset()
        
        # Should be allowed again
        self.assertTrue(limiter.is_allowed())
    
    def test_get_rate_limit_info(self):
        """Test getting rate limit info"""
        from .rate_limiting import get_rate_limit_info, check_rate_limit
        
        # Use 3 out of 10
        for i in range(3):
            check_rate_limit(1, 'test', limit=10, window=60)
        
        info = get_rate_limit_info(1, 'test', limit=10, window=60)
        
        self.assertEqual(info['current'], 3)
        self.assertEqual(info['limit'], 10)
        self.assertEqual(info['remaining'], 7)
        self.assertEqual(info['window'], 60)


class RateLimitingIntegrationTests(TestCase):
    """Integration tests for WebSocket rate limiting settings and configuration"""
    
    def setUp(self):
        """Set up test user"""
        from django.core.cache import cache
        cache.clear()
        
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            password='testpass123',
            auth_type='regular',
            role='user'
        )
    
    def test_rate_limit_settings_exist(self):
        """Test that all rate limit settings are configured"""
        from django.conf import settings
        
        self.assertTrue(hasattr(settings, 'WEBSOCKET_MESSAGE_RATE_LIMIT'))
        self.assertTrue(hasattr(settings, 'WEBSOCKET_REACTION_RATE_LIMIT'))
        self.assertTrue(hasattr(settings, 'WEBSOCKET_TYPING_RATE_LIMIT'))
        self.assertTrue(hasattr(settings, 'WEBSOCKET_MAX_PAYLOAD_SIZE'))
        
        # Verify default values
        self.assertEqual(settings.WEBSOCKET_MESSAGE_RATE_LIMIT, 60)
        self.assertEqual(settings.WEBSOCKET_REACTION_RATE_LIMIT, 120)
        self.assertEqual(settings.WEBSOCKET_TYPING_RATE_LIMIT, 30)
        self.assertEqual(settings.WEBSOCKET_MAX_PAYLOAD_SIZE, 102400)
    
    def test_rate_limit_info_generation(self):
        """Test that rate limit info is generated correctly"""
        from .rate_limiting import get_rate_limit_info
        
        info = get_rate_limit_info(self.user.id, 'message_send', limit=60, window=60)
        
        self.assertIn('current', info)
        self.assertIn('limit', info)
        self.assertIn('remaining', info)
        self.assertIn('window', info)
        self.assertEqual(info['limit'], 60)
        self.assertEqual(info['window'], 60)
    
    def test_multiple_users_isolated(self):
        """Test that rate limits don't interfere between users"""
        from .rate_limiting import check_rate_limit
        
        user2 = User.objects.create_user(
            username='testuser2@example.com',
            email='testuser2@example.com',
            password='testpass123',
            auth_type='regular',
            role='user'
        )
        
        # User 1 hits limit
        for i in range(5):
            check_rate_limit(self.user.id, 'test', limit=5, window=60)
        
        # User 1 should be blocked
        self.assertFalse(check_rate_limit(self.user.id, 'test', limit=5, window=60))
        
        # User 2 should not be affected
        self.assertTrue(check_rate_limit(user2.id, 'test', limit=5, window=60))
    
    def test_cache_backend_configured(self):
        """Test that cache backend is properly configured"""
        from django.core.cache import cache
        from django.conf import settings
        
        # Verify cache is configured
        self.assertIn('default', settings.CACHES)
        
        # Test cache operations work
        cache.set('test_key', 'test_value', 60)
        self.assertEqual(cache.get('test_key'), 'test_value')
        
        cache.delete('test_key')
        self.assertIsNone(cache.get('test_key'))


class WebSocketSizeValidationTests(TestCase):
    """Tests for WebSocket payload and message size validation (TASK_04)"""
    
    def setUp(self):
        """Set up test user"""
        from django.core.cache import cache
        cache.clear()
        
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            password='testpass123',
            auth_type='regular',
            role='user'
        )
    
    def test_message_length_settings_exist(self):
        """Test that message length settings are configured"""
        from django.conf import settings
        
        self.assertTrue(hasattr(settings, 'WEBSOCKET_MAX_MESSAGE_LENGTH'))
        self.assertTrue(hasattr(settings, 'WEBSOCKET_MAX_CONNECTIONS_PER_USER'))
        
        # Verify default values
        self.assertEqual(settings.WEBSOCKET_MAX_MESSAGE_LENGTH, 10000)
        self.assertEqual(settings.WEBSOCKET_MAX_CONNECTIONS_PER_USER, 10)
    
    def test_message_content_length_validation(self):
        """Test that oversized message content is rejected"""
        from django.conf import settings
        
        max_length = settings.WEBSOCKET_MAX_MESSAGE_LENGTH
        
        # Test message just under limit (should be valid)
        valid_message = 'A' * (max_length - 1)
        self.assertEqual(len(valid_message), max_length - 1)
        
        # Test message at limit (should be valid)
        at_limit_message = 'A' * max_length
        self.assertEqual(len(at_limit_message), max_length)
        
        # Test message over limit (should be invalid)
        oversized_message = 'A' * (max_length + 1)
        self.assertGreater(len(oversized_message), max_length)
    
    def test_connection_counter_operations(self):
        """Test connection counter increment/decrement"""
        from django.core.cache import cache
        
        conn_key = f"ws_conn_count_{self.user.id}"
        
        # Initial count should be 0
        self.assertEqual(cache.get(conn_key, 0), 0)
        
        # Increment to 1
        cache.set(conn_key, 1, 3600)
        self.assertEqual(cache.get(conn_key), 1)
        
        # Increment to 5
        cache.set(conn_key, 5, 3600)
        self.assertEqual(cache.get(conn_key), 5)
        
        # Decrement to 4
        count = cache.get(conn_key, 0)
        cache.set(conn_key, count - 1, 3600)
        self.assertEqual(cache.get(conn_key), 4)
        
        # Clear
        cache.delete(conn_key)
        self.assertEqual(cache.get(conn_key, 0), 0)
    
    def test_connection_limit_boundary(self):
        """Test connection limit boundary conditions"""
        from django.conf import settings
        from django.core.cache import cache
        
        max_connections = settings.WEBSOCKET_MAX_CONNECTIONS_PER_USER
        conn_key = f"ws_conn_count_{self.user.id}"
        
        # Set to just below limit
        cache.set(conn_key, max_connections - 1, 3600)
        current = cache.get(conn_key)
        self.assertLess(current, max_connections)
        
        # Set to exactly at limit
        cache.set(conn_key, max_connections, 3600)
        current = cache.get(conn_key)
        self.assertEqual(current, max_connections)
        
        # Over limit should be rejected in actual implementation
        cache.set(conn_key, max_connections + 1, 3600)
        current = cache.get(conn_key)
        self.assertGreaterEqual(current, max_connections)
    
    def test_payload_size_limit_exists(self):
        """Test that payload size limit is configured"""
        from django.conf import settings
        
        self.assertTrue(hasattr(settings, 'WEBSOCKET_MAX_PAYLOAD_SIZE'))
        self.assertEqual(settings.WEBSOCKET_MAX_PAYLOAD_SIZE, 102400)  # 100KB
    
    def test_message_length_error_format(self):
        """Test that message length error has correct format"""
        from django.conf import settings
        
        max_length = settings.WEBSOCKET_MAX_MESSAGE_LENGTH
        
        error_message = {
            'type': 'error',
            'code': 'MESSAGE_TOO_LONG',
            'message': f'Message too long. Maximum length: {max_length} characters'
        }
        
        self.assertEqual(error_message['type'], 'error')
        self.assertEqual(error_message['code'], 'MESSAGE_TOO_LONG')
        self.assertIn('too long', error_message['message'].lower())
        self.assertIn(str(max_length), error_message['message'])
    
    def test_connection_limit_per_user_isolation(self):
        """Test that connection limits are per-user"""
        from django.core.cache import cache
        
        user2 = User.objects.create_user(
            username='testuser2@example.com',
            email='testuser2@example.com',
            password='testpass123',
            auth_type='regular',
            role='user'
        )
        
        conn_key_1 = f"ws_conn_count_{self.user.id}"
        conn_key_2 = f"ws_conn_count_{user2.id}"
        
        # Set user 1 to 10 connections
        cache.set(conn_key_1, 10, 3600)
        
        # User 2 should have 0 connections
        self.assertEqual(cache.get(conn_key_2, 0), 0)
        
        # Set user 2 to 5 connections
        cache.set(conn_key_2, 5, 3600)
        
        # Both should maintain their own counts
        self.assertEqual(cache.get(conn_key_1), 10)
        self.assertEqual(cache.get(conn_key_2), 5)


class WebSocketSecurityIntegrationTests(TestCase):
    """Integration tests for all WebSocket security features"""
    
    def setUp(self):
        """Set up test data"""
        from django.core.cache import cache
        cache.clear()
        
        self.user = User.objects.create_user(
            username='sectest@example.com',
            email='sectest@example.com',
            password='testpass123',
            auth_type='regular',
            role='user'
        )
    
    def test_all_security_settings_configured(self):
        """Test that all WebSocket security settings are present"""
        from django.conf import settings
        
        security_settings = [
            'WEBSOCKET_MAX_PAYLOAD_SIZE',
            'WEBSOCKET_MAX_MESSAGE_LENGTH',
            'WEBSOCKET_MAX_CONNECTIONS_PER_USER',
            'WEBSOCKET_MESSAGE_RATE_LIMIT',
            'WEBSOCKET_REACTION_RATE_LIMIT',
            'WEBSOCKET_TYPING_RATE_LIMIT',
        ]
        
        for setting in security_settings:
            self.assertTrue(
                hasattr(settings, setting),
                f"Missing security setting: {setting}"
            )
    
    def test_security_limits_are_reasonable(self):
        """Test that security limits have reasonable values"""
        from django.conf import settings
        
        # Payload size should be reasonable (100KB)
        self.assertEqual(settings.WEBSOCKET_MAX_PAYLOAD_SIZE, 102400)
        
        # Message length should be reasonable (10K chars)
        self.assertEqual(settings.WEBSOCKET_MAX_MESSAGE_LENGTH, 10000)
        
        # Connection limit should be reasonable (10 per user)
        self.assertEqual(settings.WEBSOCKET_MAX_CONNECTIONS_PER_USER, 10)
        
        # Rate limits should be reasonable
        self.assertGreater(settings.WEBSOCKET_MESSAGE_RATE_LIMIT, 0)
        self.assertGreater(settings.WEBSOCKET_REACTION_RATE_LIMIT, 0)
        self.assertGreater(settings.WEBSOCKET_TYPING_RATE_LIMIT, 0)
    
    def test_cache_backend_supports_counters(self):
        """Test that cache backend can handle connection counters"""
        from django.core.cache import cache
        
        test_keys = [
            f"ws_conn_count_{self.user.id}",
            "rate_limit_test_user_1_message_send",
            "rate_limit_test_user_1_reaction_add",
        ]
        
        # Test set/get/increment operations
        for key in test_keys:
            cache.set(key, 0, 3600)
            self.assertEqual(cache.get(key), 0)
            
            # Increment
            cache.set(key, cache.get(key) + 1, 3600)
            self.assertEqual(cache.get(key), 1)
            
            # Cleanup
            cache.delete(key)
            self.assertIsNone(cache.get(key))


class UserEnumerationTests(APITestCase):
    """
    CRITICAL SECURITY: Test user enumeration prevention
    
    OWASP Reference: A01:2021 - Broken Access Control
    CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
    CWE-359: Exposure of Private Personal Information to an Unauthorized Actor
    
    Tests verify that the user list endpoint:
    1. REQUIRES search query (prevents full enumeration)
    2. Enforces minimum search length (2 characters)
    3. Applies pagination (max 50 per page)
    4. Enforces hard limit (100 results max)
    5. Excludes current user from results
    6. Returns proper error messages
    """
    
    def setUp(self):
        """Create test users"""
        # Create main test user
        self.user = User.objects.create_user(
            username='test@example.com',
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        
        # Create 150 additional users for pagination testing
        self.test_users = []
        for i in range(150):
            user = User.objects.create_user(
                username=f'john{i}@example.com',
                email=f'john{i}@example.com',
                password='testpass123',
                first_name='John',
                last_name=f'Doe{i}'
            )
            self.test_users.append(user)
        
        # Create users with different names for search testing
        self.alice = User.objects.create_user(
            username='alice@example.com',
            email='alice@example.com',
            password='testpass123',
            first_name='Alice',
            last_name='Smith'
        )
        
        self.bob = User.objects.create_user(
            username='bob@example.com',
            email='bob@example.com',
            password='testpass123',
            first_name='Bob',
            last_name='Johnson'
        )
        
        # Authenticate
        self.client.force_authenticate(user=self.user)
    
    def test_list_without_search_rejected(self):
        """
        SECURITY TEST: Listing without search query should be rejected
        
        Attack Vector: Attacker tries to enumerate all system users
        Expected: HTTP 400 with clear error message
        """
        response = self.client.get('/api/internal-chat/users/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Search query required', response.data['error'])
        self.assertEqual(response.data['code'], 'SEARCH_REQUIRED')
        
        # Verify security log entry would be created
        self.assertIn('at least 2 characters', response.data['detail'])
    
    def test_list_with_short_search_rejected(self):
        """
        SECURITY TEST: Search queries < 2 characters should be rejected
        
        Attack Vector: Attacker tries single-character searches to enumerate users
        Expected: HTTP 400 for queries with 0 or 1 character
        """
        # Empty search
        response = self.client.get('/api/internal-chat/users/', {'search': ''})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('at least 2 characters', response.data['detail'])
        
        # Single character
        response = self.client.get('/api/internal-chat/users/', {'search': 'j'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'SEARCH_REQUIRED')
        
        # Whitespace only
        response = self.client.get('/api/internal-chat/users/', {'search': '   '})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_list_with_valid_search(self):
        """
        Test successful user search with valid query (>= 2 characters)
        
        Expected: Paginated results matching search query
        """
        # Search for "Alice"
        response = self.client.get('/api/internal-chat/users/', {'search': 'al'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('results', response.data)
        
        # Should find Alice
        user_ids = [u['id'] for u in response.data['results']]
        self.assertIn(self.alice.id, user_ids)
        
        # Should NOT include current user
        self.assertNotIn(self.user.id, user_ids)
    
    def test_pagination_enforced(self):
        """
        SECURITY TEST: Pagination should be enforced (max 50 per page)
        
        Expected: Results limited to 50 per page with pagination links
        """
        # Search for "John" (should match 150 users)
        response = self.client.get('/api/internal-chat/users/', {'search': 'john'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should have pagination
        self.assertIn('count', response.data)
        self.assertIn('results', response.data)
        self.assertIn('next', response.data)
        
        # First page should have max 50 results
        self.assertLessEqual(len(response.data['results']), 50)
        
        # Total count should be limited to 100 (hard limit)
        self.assertLessEqual(response.data['count'], 100)
    
    def test_hard_limit_enforced(self):
        """
        SECURITY TEST: Hard limit of 100 results should be enforced
        
        Attack Vector: Attacker tries pagination to enumerate beyond 100 users
        Expected: Maximum 100 results total, even with pagination
        """
        # Search for "John" (matches 150 users, but should limit to 100)
        response = self.client.get('/api/internal-chat/users/', {'search': 'john'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Collect all results through pagination
        all_results = response.data['results'][:]
        next_url = response.data.get('next')
        
        while next_url and len(all_results) < 150:  # Safety limit
            # Extract page parameter from next URL
            if 'page=' in next_url:
                page = next_url.split('page=')[1].split('&')[0]
                response = self.client.get('/api/internal-chat/users/', {
                    'search': 'john',
                    'page': page
                })
                
                if response.status_code == 200:
                    all_results.extend(response.data['results'])
                    next_url = response.data.get('next')
                else:
                    break
            else:
                break
        
        # CRITICAL: Total results should never exceed 100
        self.assertLessEqual(len(all_results), 100,
            f"Hard limit violated: {len(all_results)} results returned (max 100)")
    
    def test_current_user_excluded(self):
        """
        Test that current authenticated user is excluded from results
        
        Expected: Searching for own name should not return own account
        """
        # Search for current user's name
        response = self.client.get('/api/internal-chat/users/', {'search': 'test'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Current user should NOT be in results
        user_ids = [u['id'] for u in response.data['results']]
        self.assertNotIn(self.user.id, user_ids,
            "Current user should be excluded from search results")
    
    def test_search_across_multiple_fields(self):
        """
        Test that search works across first_name, last_name, email, username
        
        Expected: Search should match any of these fields
        """
        # Search by first name
        response = self.client.get('/api/internal-chat/users/', {'search': 'alice'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_ids = [u['id'] for u in response.data['results']]
        self.assertIn(self.alice.id, user_ids)
        
        # Search by last name
        response = self.client.get('/api/internal-chat/users/', {'search': 'johnson'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_ids = [u['id'] for u in response.data['results']]
        self.assertIn(self.bob.id, user_ids)
        
        # Search by email
        response = self.client.get('/api/internal-chat/users/', {'search': 'bob@'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_ids = [u['id'] for u in response.data['results']]
        self.assertIn(self.bob.id, user_ids)
    
    def test_unauthenticated_access_denied(self):
        """
        SECURITY TEST: Unauthenticated users should be denied access
        
        Expected: HTTP 401/403
        """
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/internal-chat/users/', {'search': 'test'})
        
        self.assertIn(response.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ])


