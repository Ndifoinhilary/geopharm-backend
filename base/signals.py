from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Profile

User = settings.AUTH_USER_MODEL
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        def on_commit():
            try:
                Profile.objects.get_or_create(user=instance)
            except Exception as e:
                logger.error(f"Error creating profile for user {instance.id}: {str(e)}")

        transaction.on_commit(on_commit)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save user profile when a user is saved."""
    try:
        if hasattr(instance, 'profile'):
            instance.profile.save()
    except Profile.DoesNotExist:
        Profile.objects.create(user=instance)
    except Exception as e:
        logger.error(f"Error saving profile for user {instance.id}: {str(e)}")


@receiver(post_delete, sender=User)
def delete_user_profile(sender, instance, **kwargs):
    """Delete the user profile and all related objects when user is deleted."""
    try:
        if hasattr(instance, 'profile'):
            instance.profile.delete()
        for related_object in instance._meta.get_fields():
            if (related_object.one_to_many or related_object.one_to_one) and related_object.auto_created and not related_object.concrete:
                rel_manager = getattr(instance, related_object.get_accessor_name(), None)
                if rel_manager:
                    if hasattr(rel_manager, 'all'):
                        rel_manager.all().delete()
                    else:
                        rel_manager.delete()
    except Profile.DoesNotExist:
        pass

