def can_channel_synchronize(channel):
    return channel.mirror_channel_url and (channel.mirror_mode == "mirror")


def can_channel_reindex(channel):
    return True
