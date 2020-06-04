import os

QUETZ_GITHUB_CLIENT_ID = os.getenv('QUETZ_GITHUB_CLIENT_ID')
QUETZ_GITHUB_CLIENT_SECRET = os.getenv('QUETZ_GITHUB_CLIENT_SECRET')
QUETZ_URL = os.getenv('QUETZ_URL')
QUETZ_SQLALCHEMY_DATABASE_URL = os.getenv('QUETZ_SQLALCHEMY_DATABASE_URL')
QUETZ_SESSION_SECRET = os.getenv('QUETZ_SESSION_SECRET')

https_only = True
https_only_str = os.getenv('QUETZ_SESSION_HTTPS_ONLY', None)
if https_only_str and https_only_str.lower() == 'false':
    https_only = False

QUETZ_SESSION_HTTPS_ONLY = https_only
