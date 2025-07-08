"""
Django command to pause execution until a database is available
"""
import time

from psycopg2 import OperationalError as Psycopg2OperationalError
from django.db.utils import OperationalError

from django.core.management import BaseCommand


class Command(BaseCommand):
    """Django command to pause execution until a database is available"""

    def handle(self, *args, **options):
        self.stdout.write('Waiting for database...')
        db_up = False
        while not db_up:
            try:
                self.check(databases=['default'])
                db_up = True
            except (OperationalError, Psycopg2OperationalError):
                self.stdout.write('Database not available waiting 1 second')
                time.sleep(1)

        self.stdout.write(self.style.SUCCESS("Database available"))
