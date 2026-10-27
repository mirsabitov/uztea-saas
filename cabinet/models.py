from django.conf import settings
from django.db import models


class MemberProfile(models.Model):
    """Things a member adds in "My profile" that the application form does not have."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='member_profile')
    photo = models.ImageField(upload_to='members/photos/', blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Profile of {self.user}'


class ProfileChange(models.Model):
    """What a member changed in "My profile" (old → new), for staff to see."""
    membership = models.ForeignKey('app.Membership', on_delete=models.CASCADE, related_name='profile_changes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.membership_id} changed {", ".join(self.changes)}'
