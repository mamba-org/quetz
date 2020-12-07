# Copyright 2020 QuantStack, Codethink Ltd
# Distributed under the terms of the Modified BSD License.

import uuid

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request
from starlette.responses import RedirectResponse

from quetz.deps import get_config, get_dao

from .config import Config
from .dao import Dao
from .dao_google import get_user_by_google_identity

router = APIRouter(prefix='/auth/google')
oauth = OAuth()


def register(config):
    # Register the app here: https://console.developers.google.com/apis/credentials
    oauth.register(
        name="google",
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        server_metadata_url=(
            'https://accounts.google.com/.well-known/openid-configuration'
        ),
        client_kwargs={'scope': 'openid email profile'},
        prompt='select_account',
    )


async def validate_token(token):
    resp = await oauth.google.get(
        'https://openidconnect.googleapis.com/v1/userinfo', token=token
    )
    return resp.status_code != 401


@router.get('/login')
async def login(request: Request):
    google = oauth.create_client('google')
    redirect_uri = request.url_for('authorize_google')
    return await google.authorize_redirect(request, redirect_uri)


@router.get('/enabled')
async def enabled():
    """Entrypoint used by frontend to show the login button."""
    return True


@router.get('/authorize', name='authorize_google')
async def authorize(
    request: Request, dao: Dao = Depends(get_dao), config: Config = Depends(get_config)
):
    token = await oauth.google.authorize_access_token(request)
    profile = await oauth.google.parse_id_token(request, token)
    user = get_user_by_google_identity(dao, profile, config)

    request.session['user_id'] = str(uuid.UUID(bytes=user.id))

    request.session['identity_provider'] = 'google'

    request.session['token'] = token

    return RedirectResponse('/')


@router.route('/revoke')
async def revoke(request):
    return RedirectResponse('https://myaccount.google.com/permissions')
