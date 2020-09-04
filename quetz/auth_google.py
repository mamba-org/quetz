# Copyright 2020 QuantStack, Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import uuid

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse

from .dao_google import get_user_by_google_identity
from .database import get_session

router = APIRouter()
oauth = OAuth()


def register(config):
    # Register the app here: https://console.developers.google.com/apis/credentials
    oauth.register(
        name='google',
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        server_metadata_url=(
            'https://accounts.google.com' '/.well-known/openid-configuration'
        ),
        client_kwargs={'scope': 'openid email profile'},
        quetz_db_url=config.sqlalchemy_database_url,
        prompt='select_account',
    )


async def validate_token(token):
    resp = await oauth.google.get(
        'https://openidconnect.googleapis.com/v1/userinfo', token=token
    )
    if resp.status_code == 401:
        return False
    return True


@router.route('/auth/google/login')
async def login_google(request: Request):
    google = oauth.create_client('google')
    redirect_uri = request.url_for('authorize_google')
    return await google.authorize_redirect(request, redirect_uri)


@router.route('/auth/google/authorize', name='authorize_google')
async def authorize(request: Request):
    token = await oauth.google.authorize_access_token(request)
    profile = await oauth.google.parse_id_token(request, token)
    db = get_session(oauth.google.server_metadata['quetz_db_url'])
    try:
        user = get_user_by_google_identity(db, profile)
    finally:
        db.close()

    request.session['user_id'] = str(uuid.UUID(bytes=user.id))

    request.session['identity_provider'] = 'google'

    request.session['token'] = token

    return RedirectResponse('/')


@router.route('/auth/google/revoke')
async def revoke(request):
    return RedirectResponse('https://myaccount.google.com/permissions')
