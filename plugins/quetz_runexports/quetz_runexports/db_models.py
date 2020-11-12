from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import backref, relationship

from quetz.db_models import UUID, Base


class PackageVersionMetadata(Base):
    __tablename__ = "quetz_runexports_package_version_metadata"

    version_id = Column(UUID, ForeignKey("package_versions.id"), primary_key=True)
    package_version = relationship(
        "PackageVersion",
        backref=backref(
            "runexports",
            uselist=False,
            cascade="delete,all",
        ),
    )
    data = Column(String)
