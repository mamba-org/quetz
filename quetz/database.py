# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from quetz import config

Base = declarative_base()


def _get_engine():
    engine = create_engine(
        config.sqlalchemy_database_url,
        connect_args={'check_same_thread': False},
        echo=False
    )
    return engine


def get_session():
    return sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())()


def init_db():
    Base.metadata.create_all(_get_engine())
