# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import json
import uuid

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, Request
from starlette.responses import RedirectResponse

from quetz.deps import get_db

from .dao_github import get_user_by_github_identity

router = APIRouter()
oauth = OAuth()


def register(config, client_kwargs=None):
    # Register the app here: https://github.com/settings/applications/new

    if client_kwargs is None:
        client_kwargs = {}

    oauth.register(
        name="github",
        client_id=config.github_client_id,
        client_secret=config.github_client_secret,
        access_token_url='https://github.com/login/oauth/access_token',
        access_token_params=None,
        authorize_url='https://github.com/login/oauth/authorize',
        authorize_params=None,
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'user:email', **client_kwargs},
        quetz_db_url=config.sqlalchemy_database_url,
        default_user_role=config.users_default_role
        if config.configured_section("users")
        else None,
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
    redirect_uri = request.url_for('authorize_github')
    return await github.authorize_redirect(request, redirect_uri)


@router.get('/auth/github/authorize', name='authorize_github')
async def authorize(request: Request, db=Depends(get_db)):
    token = await oauth.github.authorize_access_token(request)
    resp = await oauth.github.get('user', token=token)
    profile = resp.json()
    default_user_role = oauth.github.server_metadata['default_user_role']
    try:
        user = get_user_by_github_identity(db, profile, default_user_role)
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
        f'https://github.com/settings/connections/applications/{client_id}'
    )
