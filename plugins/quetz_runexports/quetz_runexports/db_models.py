from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import backref, relationship

from quetz.db_models import UUID, Base


class PackageVersionMetadata(Base):
    __tablename__ = "quetz_runexports_package_version_metadata"

    id = Column(UUID, primary_key=True)
    version_id = Column(UUID, ForeignKey("package_versions.id"))
    package_version = relationship(
        "PackageVersion", backref=backref("runexports", uselist=False)
    )
    run_exports = Column(String)
