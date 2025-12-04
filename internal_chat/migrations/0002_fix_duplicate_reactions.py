# Generated migration to fix duplicate reactions before applying unique constraint
from django.db import migrations


def remove_duplicate_reactions(apps, schema_editor):
    """
    Keep only the most recent reaction per user per message.
    Delete older duplicate reactions before applying unique constraint.
    """
    MessageReaction = apps.get_model('internal_chat', 'MessageReaction')
    
    # Find all message-user combinations that have multiple reactions
    from django.db.models import Count
    duplicates = (
        MessageReaction.objects
        .values('message_id', 'user_id')
        .annotate(count=Count('id'))
        .filter(count__gt=1)
    )
    
    for dup in duplicates:
        message_id = dup['message_id']
        user_id = dup['user_id']
        
        # Get all reactions for this message-user pair, ordered by creation date
        reactions = MessageReaction.objects.filter(
            message_id=message_id,
            user_id=user_id
        ).order_by('-created_at')
        
        # Keep the most recent one, delete the rest
        reactions_to_delete = reactions[1:]
        for reaction in reactions_to_delete:
            reaction.delete()


def reverse_func(apps, schema_editor):
    # No need to reverse - we're just cleaning data
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('internal_chat', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_reactions, reverse_func),
    ]
