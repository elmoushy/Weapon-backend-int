from django.apps import AppConfig


class InternalChatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'internal_chat'
    verbose_name = 'Internal Chat'
    
    def ready(self):
        """
        Import signals when app is ready
        """
        import internal_chat.signals  # noqa
