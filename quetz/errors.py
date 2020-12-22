# Copyright 2020 Codethink Ltd
# Distributed under the terms of the Modified BSD License.


class QuetzError(Exception):
    pass


class DBError(QuetzError):
    pass


class ConfigError(QuetzError):
    pass


class ValidationError(QuetzError):
    pass


class QuotaError(ValidationError):
    pass


class TaskError(QuetzError):
    pass
