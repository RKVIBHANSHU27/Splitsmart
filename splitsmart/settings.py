from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR      = Path(__file__).resolve().parent.parent
SECRET_KEY    = os.getenv('SECRET_KEY', 'django-insecure-key')

DEBUG         = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.elasticbeanstalk.com']

STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  

MEDIA_URL   = '/media/'
MEDIA_ROOT  = BASE_DIR / 'media'