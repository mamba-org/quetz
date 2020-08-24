# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


def _get_engine(db_url):
    engine = create_engine(
        db_url,
        connect_args={'check_same_thread': False},
        echo=False
    )
    return engine


def get_session(db_url):
    return sessionmaker(autocommit=False, autoflush=False,
                        bind=_get_engine(db_url))()


def init_db(db_url):
    Base.metadata.create_all(_get_engine(db_url))
