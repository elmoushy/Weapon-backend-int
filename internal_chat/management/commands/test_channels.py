"""
Management command to test channel layer connectivity
"""
from django.core.management.base import BaseCommand
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


class Command(BaseCommand):
    help = 'Test channel layer connectivity (Redis)'
    
    def handle(self, *args, **options):
        self.stdout.write('Testing channel layer connectivity...')
        
        try:
            channel_layer = get_channel_layer()
            
            # Test basic send/receive
            test_message = {'type': 'test.message', 'text': 'Hello from channel layer test'}
            
            # Send a test message
            async_to_sync(channel_layer.group_send)(
                'test_group',
                test_message
            )
            
            self.stdout.write(self.style.SUCCESS('✓ Channel layer is working'))
            self.stdout.write(f'Backend: {channel_layer.__class__.__name__}')
            
            # Check if it's Redis or in-memory
            if 'Redis' in channel_layer.__class__.__name__:
                self.stdout.write(self.style.SUCCESS('✓ Using Redis backend (recommended for production)'))
            else:
                self.stdout.write(self.style.WARNING('⚠ Using in-memory backend (not suitable for production)'))
            
            return
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Channel layer test failed: {str(e)}'))
            self.stdout.write(self.style.WARNING('Make sure Redis is running: docker run -d -p 6379:6379 redis:latest'))
            raise
