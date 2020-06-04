import random
import uuid
from quetz.database import init_db, SessionLocal
from quetz.db_models import (User, Identity, Profile, Channel, ChannelMember, Package,
                             PackageMember, ApiKey)

init_db()

db = SessionLocal()

testUsers = []

try:
    for index, username in enumerate(['alice', 'bob', 'carol', 'dave']):
        user = User(id=uuid.uuid4().bytes, username=username)

        identity = Identity(
            provider='dummy',
            identity_id=str(index),
            username=username,
        )

        profile = Profile(
            name=username.capitalize(),
            avatar_url='/static/avatar.jpg')

        user.identities.append(identity)
        user.profile = profile
        db.add(user)
        testUsers.append(user)

    for channel_index in range(30):
        channel = Channel(
            name=f'Channel {channel_index}',
            description=f'Description of Channel {channel_index}',
            private=False)

        for package_index in range(random.randint(5, 100)):
            package = Package(
                name=f'Package {package_index}',
                description=f'Description of Package {package_index}')
            channel.packages.append(package)

            test_user = testUsers[random.randint(0, len(testUsers) - 1)]
            package_member = PackageMember(
                package=package,
                channel=channel,
                user=test_user,
                role='owner')

            db.add(package_member)

            if channel_index == 0 and package_index == 0:
                # create API key
                key = 'E_KaBFstCKI9hTdPM7DQq56GglRHf2HW7tQtq6si370'

                key_user = User(id=uuid.uuid4().bytes)

                api_key = ApiKey(
                    key=key,
                    description='test API key',
                    user=key_user,
                    owner=test_user
                )
                db.add(api_key)

                key_package_member = PackageMember(
                    user=key_user,
                    channel_name=channel.name,
                    package_name=package.name,
                    role='maintainer')
                db.add(key_package_member)

        db.add(channel)

        channel_member = ChannelMember(
            channel=channel,
            user=testUsers[random.randint(0, len(testUsers)-1)],
            role='owner')

        db.add(channel_member)
    db.commit()
finally:
    db.close()
