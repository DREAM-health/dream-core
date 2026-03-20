import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

from apps.accounts.permissions import HasAnyRole
import inspect

print(inspect.signature(HasAnyRole('TEST').has_permission))