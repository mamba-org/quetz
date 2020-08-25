Configuration
-------------

Quetz configuration can be set from various places, all of them should not necessarily exist.
Multiple declaration of the same entry overrides its value (from lowest to highest importance):

- system-wide, shared by all deployments on this Operating System::

    /etc/xdg/xdg-ubuntu/quetz/config.toml

- user profile, shared by all deployments started by this user::

    ~/.config/quetz/config.toml

- deployment file, specified for a deployment
- file specified by the environment variable "QUETZ_CONFIG_FILE"
- entry specified by the environment variable "QUETZ_{SECTION}_{ENTRY}"
