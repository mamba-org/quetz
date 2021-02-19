def can_channel_synchronize(channel):
    return channel.mirror_channel_url and (channel.mirror_mode == "mirror")


def can_channel_synchronize_metrics(channel):
    return not channel.mirror_channel_url


def can_channel_generate_indexes(channel):
    return True


def can_channel_validate_package_cache(channel):
    return True


def can_channel_reindex(channel):
    return True


def can_cleanup(channel):
    return True
