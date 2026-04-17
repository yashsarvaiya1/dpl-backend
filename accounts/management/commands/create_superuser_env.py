import os
from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    help = 'Create a superuser from environment variables (non-interactive)'

    def handle(self, *args, **kwargs):
        mobile_number = os.environ.get('SUPERUSER_MOBILE', '8511383287')
        password      = os.environ.get('SUPERUSER_PASSWORD')
        username      = os.environ.get('SUPERUSER_USERNAME', 'ONLINE')

        if not password:
            self.stderr.write('ERROR: SUPERUSER_PASSWORD environment variable is not set.')
            return

        if User.objects.filter(mobile_number=mobile_number).exists():
            self.stdout.write(f'Superuser with mobile {mobile_number} already exists. Skipping.')
            return

        user = User.objects.create_superuser(
            mobile_number=mobile_number,
            password=password,
        )
        user.username = username
        user.save(update_fields=['username'])

        self.stdout.write(self.style.SUCCESS(
            f'Superuser created — mobile: {mobile_number}, username: {username}'
        ))
