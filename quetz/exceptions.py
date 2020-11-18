class PackageError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        return f"{class_name}(detail={self.detail!r})"
