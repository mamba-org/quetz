# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from typing import List
from fastapi import Depends, FastAPI, HTTPException, status, Request, File, UploadFile, APIRouter
from fastapi.responses import HTMLResponse

from starlette.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import uuid
import secrets
import shutil
import os
import sys
import tarfile
import json
import subprocess
from io import BytesIO
from zipfile import ZipFile
import zstandard

from quetz import auth_github
from quetz import config
from quetz.dao import Dao
from .database import SessionLocal
from quetz import rest_models
from quetz import db_models
from quetz import authorization

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=config.QUETZ_SESSION_SECRET,
    https_only=config.QUETZ_SESSION_HTTPS_ONLY)

api_router = APIRouter()

app.include_router(auth_github.router)

# Dependency injection

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_dao(db: Session = Depends(get_db)):
    return Dao(db)


def get_session(request: Request):
    return request.session


def get_rules(request: Request, session: dict = Depends(get_session),
              db: Session = Depends(get_db)):
    return authorization.Rules(request.headers.get('x-api-key'), session, db)


def get_channel_or_fail(channel_name: str, dao: Dao = Depends(get_dao)) -> db_models.Channel:
    channel = dao.get_channel(channel_name)

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Channel {channel_name} not found')

    return channel


def get_package_or_fail(
        package_name: str,
        channel: db_models.Channel = Depends(get_channel_or_fail),
        dao: Dao = Depends(get_dao)) -> db_models.Package:

    package = dao.get_package(channel.name, package_name)
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Package {channel.name}/{package_name} not found')

    return package


# helper functions

async def check_token_revocation(session):
    identity_provider = session.get('identity_provider')
    if identity_provider and identity_provider == 'github':
        valid = await auth_github.validate_token(session.get('token'))
        if not valid:
            logout(session)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Not logged in',
            )

def logout(session):
    session.pop('user_id', None)
    session.pop('identity_provider', None)
    session.pop('token', None)

# endpoints
@app.route('/auth/logout')
async def route_logout(request):
    logout(request.session)
    return RedirectResponse('/')


@api_router.get('/dummylogin/{username}', tags=['dev'])
def dummy_login(
        username: str,
        dao: Dao = Depends(get_dao),
        session=Depends(get_session)):
    user = dao.get_user_by_username(username)

    logout(session)
    session['user_id'] = str(uuid.UUID(bytes=user.id))

    session['identity_provider'] = 'dummy'
    return RedirectResponse('/')


@api_router.get('/me', response_model=rest_models.Profile, tags=['users'])
async def me(
        session: dict = Depends(get_session),
        dao: Dao = Depends(get_dao),
        auth: authorization.Rules = Depends(get_rules)):
    """Returns your quetz profile"""

    # Check if token is still valid
    await check_token_revocation(session)

    user_id = auth.assert_user()

    profile = dao.get_profile(user_id)
    profile.user.id = str(uuid.UUID(bytes=profile.user.id))
    return profile


@api_router.get('/users', response_model=List[rest_models.User], tags=['users'])
def get_users(
        dao: Dao = Depends(get_dao),
        skip: int = 0, limit: int = 10, q: str = None):
    user_list = dao.get_users(skip, limit, q)
    for user in user_list:
        user.id = str(uuid.UUID(bytes=user.id))

    return user_list


@api_router.get('/users/{username}', response_model=rest_models.User, tags=['users'])
def get_user(
        username: str,
        dao: Dao = Depends(get_dao)):
    user = dao.get_user_by_username(username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'User {username} not found')

    user.id = str(uuid.UUID(bytes=user.id))

    return user


@api_router.get('/channels', response_model=List[rest_models.Channel], tags=['channels'])
def get_channels(
        dao: Dao = Depends(get_dao),
        skip: int = 0, limit: int = 10, q: str = None):
    """List all channels"""

    return dao.get_channels(skip, limit, q)


@api_router.get('/channels/{channel_name}', response_model=rest_models.Channel, tags=['channels'])
def get_channel(channel: db_models.Channel = Depends(get_channel_or_fail)):
    return channel


@api_router.post('/channels', status_code=201, tags=['channels'])
def post_channel(
        new_channel: rest_models.Channel,
        dao: Dao = Depends(get_dao),
        auth: authorization.Rules = Depends(get_rules)):

    user_id = auth.assert_user()

    channel = dao.get_channel(new_channel.name)

    if channel:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Channel {new_channel.name} exists')

    dao.create_channel(new_channel, user_id, authorization.OWNER)


@api_router.get('/channels/{channel_name}/packages', response_model=List[rest_models.Package],
         tags=['packages'])
def get_packages(
        channel: db_models.Channel = Depends(get_channel_or_fail),
        dao: Dao = Depends(get_dao),
        skip: int = 0, limit: int = 10, q: str = None):

    return dao.get_packages(channel.name, skip, limit, q)


@api_router.get('/channels/{channel_name}/packages/{package_name}', response_model=rest_models.Package,
         tags=['packages'])
def get_package(
        package: db_models.Package = Depends(get_package_or_fail)):
    return package


@api_router.post('/channels/{channel_name}/packages', status_code=201, tags=['packages'])
def post_package(
        new_package: rest_models.Package,
        channel: db_models.Channel = Depends(get_channel_or_fail),
        auth: authorization.Rules = Depends(get_rules),
        dao: Dao = Depends(get_dao)):

    user_id = auth.assert_user()
    package = dao.get_package(channel.name, new_package.name)
    if package:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Package {channel.name}/{new_package.name} exists')

    dao.create_package(channel.name, new_package, user_id, authorization.OWNER)


@api_router.get('/channels/{channel_name}/members', response_model=List[rest_models.Member],
         tags=['channels'])
def get_channel_members(
        channel: db_models.Channel = Depends(get_channel_or_fail),
        dao: Dao = Depends(get_dao)):

    member_list = dao.get_channel_members(channel.name)
    for member in member_list:
        # force loading of profile before changing attributes to prevent sqlalchemy errors.
        # TODO: don't abuse db models for this.

        member.user.profile
        setattr(member.user, 'id', str(uuid.UUID(bytes=member.user.id)))

    return member_list


@api_router.post('/channels/{channel_name}/members', status_code=201, tags=['channels'])
def post_channel_member(
        new_member: rest_models.PostMember,
        channel: db_models.Channel = Depends(get_channel_or_fail),
        dao: Dao = Depends(get_dao),
        auth: authorization.Rules = Depends(get_rules)):

    auth.assert_add_channel_member(channel.name, new_member.role)

    channel_member = dao.get_channel_member(channel.name, new_member.username)
    if channel_member:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Member {new_member.username} in {channel.name} exists')

    dao.create_channel_member(channel.name, new_member)


@api_router.get('/channels/{channel_name}/packages/{package_name}/members',
         response_model=List[rest_models.Member], tags=['packages'])
def get_package_members(
        package: db_models.Package = Depends(get_package_or_fail),
        dao: Dao = Depends(get_dao)):

    member_list = dao.get_package_members(package.channel.name, package.name)

    for member in member_list:
        # force loading of profile before changing attributes to prevent sqlalchemy errors.
        # TODO: don't abuse db models for this.
        member.user.profile
        setattr(member.user, 'id', str(uuid.UUID(bytes=member.user.id)))

    return member_list


@api_router.post('/channels/{channel_name}/packages/{package_name}/members', status_code=201,
          tags=['packages'])
def post_package_member(
        new_member: rest_models.PostMember,
        package: db_models.Package = Depends(get_package_or_fail),
        dao: Dao = Depends(get_dao),
        auth: authorization.Rules = Depends(get_rules)):

    auth.assert_add_package_member(package.channel.name, package.name, new_member.role)

    channel_member = dao.get_package_member(package.channel.name, package.name, new_member.username)
    if channel_member:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Member {new_member.username} in {package.channel.name}/{package.name} exists')

    dao.create_package_member(package.channel.name, package.name, new_member)


@api_router.get('/channels/{channel_name}/packages/{package_name}/versions',
         response_model=List[rest_models.PackageVersion], tags=['packages'])
def get_package_versions(
        package: db_models.Package = Depends(get_package_or_fail),
        dao: Dao = Depends(get_dao)):

    version_profile_list = dao.get_package_versions(package)
    version_list = []

    for version, profile, api_key_profile in version_profile_list:
        # TODO: don't abuse db models for this.
        version.id = str(uuid.UUID(bytes=version.id))
        version.info = json.loads(version.info)
        version.uploader = profile if profile else api_key_profile
        version_list.append(version)

    return version_list


@api_router.get('/api-keys', response_model=List[rest_models.ApiKey], tags=['API keys'])
def get_api_keys(
        dao: Dao = Depends(get_dao),
        auth: authorization.Rules = Depends(get_rules)):
    """Get API keys for current user"""

    user_id = auth.assert_user()
    api_key_list = dao.get_package_api_keys(user_id)
    api_channel_key_list = dao.get_channel_api_keys(user_id)

    from itertools import groupby

    return [rest_models.ApiKey(
        key=api_key.key,
        description=api_key.description,
        roles=[rest_models.CPRole(
            channel=member.channel_name,
            package=member.package_name if hasattr(member, 'package_name') else None,
            role=member.role
        ) for member, api_key in member_key_list]
    ) for api_key, member_key_list in groupby(
        [*api_key_list, *api_channel_key_list],
        lambda member_api_key: member_api_key[1])]


@api_router.post('/api-keys', status_code=201, tags=['API keys'])
def post_api_key(
        api_key: rest_models.BaseApiKey,
        dao: Dao = Depends(get_dao),
        auth: authorization.Rules = Depends(get_rules)):

    auth.assert_create_api_key_roles(api_key.roles)

    user_id = auth.assert_user()

    key = secrets.token_urlsafe(32)
    dao.create_api_key(user_id, api_key, key)


@api_router.post('/channels/{channel_name}/packages/{package_name}/files/', status_code=201,
          tags=['files'])
def post_file(
        files: List[UploadFile] = File(...),
        package: db_models.Package = Depends(get_package_or_fail),
        dao: Dao = Depends(get_dao),
        auth: authorization.Rules = Depends(get_rules)):

    handle_package_files(package.channel.name, files, dao, auth, package=package)


@api_router.post('/channels/{channel_name}/files/', status_code=201, tags=['files'])
def post_file(
        files: List[UploadFile] = File(...),
        channel: db_models.Channel = Depends(get_channel_or_fail),
        dao: Dao = Depends(get_dao),
        auth: authorization.Rules = Depends(get_rules)):

    handle_package_files(channel.name, files, dao, auth)


def handle_package_files(channel_name, files, dao, auth, package=None):
    channel_dir = f'channels/{channel_name}'
    for file in files:
        if file.filename.endswith(".conda"):
            with ZipFile(file.file._file) as zf:
                infotar = [_ for _ in zf.namelist()
                           if _.startswith("info-")][0]
                with zf.open(infotar) as zfobj:
                    if infotar.endswith(".zst"):
                        zstd = zstandard.ZstdDecompressor()
                        # zstandard.stream_reader cannot seek backwards
                        # and tarfile.extractfile() seeks backwards
                        fobj = BytesIO(zstd.stream_reader(zfobj).read())
                    else:
                        fobj = zfobj
                    with tarfile.open(fileobj=fobj, mode="r") as tar:
                        info = json.load(tar.extractfile("info/index.json"))
        else:
            with tarfile.open(fileobj=file.file._file, mode="r:bz2") as tar:
                info = json.load(tar.extractfile('info/index.json'))

        package_name = info['name']

        parts = file.filename.split('-')
        if package and (parts[0] != package.name or info['name'] != package.name):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

        if not package and not dao.get_package(channel_name, package_name):
            dao.create_package(
                channel_name,
                rest_models.Package(name=package_name, description='n/a'),
                auth.assert_user(),
                authorization.OWNER
            )

        auth.assert_upload_file(channel_name, package_name)

        try:
            dao.create_version(
                channel_name=channel_name,
                package_name=package_name,
                platform=info['subdir'],
                version=info['version'],
                build_number=info['build_number'],
                build_string=info['build'],
                filename=file.filename,
                info=json.dumps(info),
                uploader_id=user_id)
        except IntegrityError:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT)

        dir = f'{channel_dir}/{info["subdir"]}/'
        os.makedirs(dir, exist_ok=True)

        file.file._file.seek(0)
        with open(f'{dir}/{file.filename}', 'wb') as my_file:
            shutil.copyfileobj(file.file, my_file)

        user_id = auth.assert_user()

    subprocess.run(['conda', 'index', channel_dir])

app.include_router(
    api_router,
    prefix="/api",
)

@app.get("/api/.*", status_code=404, include_in_schema=False)
def invalid_api():
    return None


app.mount("/channels", StaticFiles(directory='channels', html=True), name="channels")


if os.path.isfile('quetz_frontend/dist/index.html'):
    print('dev frontend found')
    app.mount("/", StaticFiles(directory='quetz_frontend/dist', html=True), name="frontend")
elif os.path.isfile(f'{sys.prefix}/share/quetz/frontend/index.html'):
    print('installed frontend found')
    app.mount("/", StaticFiles(directory=f'{sys.prefix}/share/quetz/frontend/', html=True), name="frontend")
else:
    print(f'basic frontend')
    basic_frontend_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'basic_frontend')
    app.mount("/", StaticFiles(directory=basic_frontend_dir, html=True), name="frontend")
