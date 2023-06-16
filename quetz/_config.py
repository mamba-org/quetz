from typing import Any, Dict, Optional

from pydantic import BaseModel, BaseSettings
from pydantic.fields import ModelField


# https://github.com/pydantic/pydantic/issues/1937#issuecomment-695313040
class DyanamicallyExtendableSetting(BaseSettings):
    @classmethod
    def add_fields(cls, **field_definitions: Any):
        new_fields: Dict[str, ModelField] = {}
        new_annotations: Dict[str, Optional[type]] = {}

        for f_name, f_def in field_definitions.items():
            if isinstance(f_def, tuple):
                try:
                    f_annotation, f_value = f_def
                except ValueError as e:
                    raise Exception(
                        'field definitions should either be a tuple '
                        'of (<type>, <default>) or just a'
                        'default value, unfortunately this means tuples as '
                        'default values are not allowed'
                    ) from e
            else:
                f_annotation, f_value = None, f_def

            if f_annotation:
                new_annotations[f_name] = f_annotation

            new_fields[f_name] = ModelField.infer(
                name=f_name,
                value=f_value,
                annotation=f_annotation,
                class_validators=None,
                config=cls.__config__,
            )

        cls.__fields__.update(new_fields)
        cls.__annotations__.update(new_annotations)


class SettingsGeneral(BaseModel):
    package_unpack_threads: int = 1
    frontend_dir: str = ""
    redirect_http_to_https: bool = False


class SettingsCORS(BaseModel):
    allow_origins: list = []
    allow_credentials: bool = True
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]


class SettingsGitHub(BaseModel):
    client_id: str
    client_secret: str


class SettingsGitLab(BaseModel):
    url: str = "https://gitlab.com"
    client_id: str
    client_secret: str


class SettingsAzureAD(BaseModel):
    client_id: str
    client_secret: str
    tenant_id: str


class SettingsSQLAlchemy(BaseModel):
    database_url: str
    database_plugin_path: str = ""
    echo_sql: bool = False
    postgres_pool_size: int = 100
    postgres_max_overflow: int = 100


class SettingsSession(BaseModel):
    secret: str
    https_only: bool = True


class SettingsLocalStore(BaseModel):
    redirect_enabled: bool = False
    redirect_endpoint: str = "/files"
    redirect_secret: str = ""
    redirect_expiration: int = 3600


class SettingsS3(BaseModel):
    access_key: str = ""
    secret_key: str = ""
    url: str = ""
    region: str = ""
    bucket_prefix: str = ""
    bucket_suffix: str = ""


class SettingsAzureBlob(BaseModel):
    account_name: str = ""
    account_access_key: str = ""
    conn_str: str = ""
    container_prefix: str = ""
    container_suffix: str = ""


class SettingsGCS(BaseModel):
    project: str = ""
    token: str = ""
    bucket_prefix: str = ""
    bucket_suffix: str = ""
    cache_timeout: int | None = None
    region: str | None = None


class SettingsGoogle(BaseModel):
    client_id: str
    client_secret: str


class SettingsLogging(BaseModel):
    level: str = "INFO"
    file: str = ""


class SettingsUsers(BaseModel):
    admins: list[str] = []
    maintainers: list[str] = []
    members: list[str] = []
    default_role: str = ""
    collect_emails: bool = False
    create_default_channel: bool = False


class SettingsWorker:
    type: str = "thread"
    redis_ip: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0


class SettingsPlugins(BaseModel):
    enabled: list[str] = []


class SettingsMirroring(BaseModel):
    batch_length: int = 10
    batch_size: int = 10**8
    num_parallel_downloads: int = 10


class SettingsQuotas(BaseModel):
    channel_quota: int


class SettingsProfiling(BaseModel):
    enable_sampling: bool = False
    interval_seconds: float = 0.001


class Settings(DyanamicallyExtendableSetting):
    general: SettingsGeneral = SettingsGeneral()
    cors: Optional[SettingsCORS] = None
    github: Optional[SettingsGitHub] = None
    gitlab: Optional[SettingsGitLab] = None
    azuread: Optional[SettingsAzureAD] = None
    sqlalchemy: SettingsSQLAlchemy
    session: SettingsSession
    local_store: SettingsLocalStore = SettingsLocalStore()
    s3: Optional[SettingsS3] = None
    azure_blob: Optional[SettingsAzureBlob] = None
    gcs: Optional[SettingsGCS] = None
    google: Optional[SettingsGoogle] = None
    logging: Optional[SettingsLogging] = None
    users: Optional[SettingsUsers] = None
    worker: Optional[SettingsWorker] = None
    plugins: SettingsPlugins = SettingsPlugins()
    mirroring: SettingsMirroring = SettingsMirroring()
    quotas: Optional[SettingsQuotas] = None
    profiling: Optional[SettingsProfiling] = None

    class Config:
        env_prefix = "quetz__"
        env_nested_delimiter = "__"
