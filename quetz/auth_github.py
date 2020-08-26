# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from starlette.responses import RedirectResponse
from fastapi import APIRouter, Request
from authlib.integrations.starlette_client import OAuth
from .database import get_session
from .dao_github import get_user_by_github_identity
import json
import uuid

router = APIRouter()
oauth = OAuth()


def register(config):
    # Register the app here: https://github.com/settings/applications/new
    oauth.register(
        name='github',
        client_id=config.github_client_id,
        client_secret=config.github_client_secret,
        access_token_url='https://github.com/login/oauth/access_token',
        access_token_params=None,
        authorize_url='https://github.com/login/oauth/authorize',
        authorize_params=None,
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'user:email'},
        quetz_db_url=config.sqlalchemy_database_url
    )


async def validate_token(token):
    # identity = get_identity(db, identity_id)
    resp = await oauth.github.get('user', token=json.loads(token))
    if resp.status_code == 401:
        return False
    return True


@router.route('/auth/github/login')
async def login(request):
    github = oauth.create_client('github')
    redirect_uri = request.url_for('authorize')
    return await github.authorize_redirect(request, redirect_uri)


@router.route('/auth/github/authorize')
async def authorize(request: Request):
    token = await oauth.github.authorize_access_token(request)
    resp = await oauth.github.get('user', token=token)
    profile = resp.json()
    db = get_session(oauth.github.server_metadata['quetz_db_url'])
    try:
        user = get_user_by_github_identity(db, profile)
    finally:
        db.close()

    request.session['user_id'] = str(uuid.UUID(bytes=user.id))

    request.session['identity_provider'] = 'github'

    request.session['token'] = json.dumps(token)

    resp = RedirectResponse('/')

    return resp


@router.route('/auth/github/revoke')
async def revoke(request):
    client_id = oauth.github.client_id
    return RedirectResponse(
        f'https://github.com/settings/connections/applications/{client_id}')
