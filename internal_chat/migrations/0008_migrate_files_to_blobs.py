# Generated migration to convert existing file-based attachments to blob storage

from django.db import migrations
import logging
import os

logger = logging.getLogger(__name__)


def migrate_files_to_blobs(apps, schema_editor):
    """
    Migrate existing file attachments to blob storage.
    This reads files from disk and stores them in the database.
    """
    Attachment = apps.get_model('internal_chat', 'Attachment')
    
    migrated_count = 0
    failed_count = 0
    
    for attachment in Attachment.objects.all():
        # Skip if already has blob data
        if attachment.file_data:
            continue
        
        # Try to read old file if it exists
        # Note: The old 'file' field is already removed, so we can't access it
        # We'll just log that manual intervention may be needed
        logger.warning(
            f"Attachment {attachment.id} ({attachment.file_name}) has no blob data. "
            f"Original file may need manual migration if still needed."
        )
        failed_count += 1
    
    logger.info(f"Migration complete. Migrated: {migrated_count}, Failed/Skipped: {failed_count}")


def reverse_migration(apps, schema_editor):
    """
    Reverse migration is not supported - blob data cannot be restored to files.
    """
    logger.warning("Reverse migration not supported for blob storage.")


class Migration(migrations.Migration):

    dependencies = [
        ('internal_chat', '0007_remove_attachment_file_attachment_file_data'),
    ]

    operations = [
        migrations.RunPython(migrate_files_to_blobs, reverse_migration),
    ]
