from pathlib import Path

from vendorlens.services.storage import LocalFileStorage


def get_storage() -> LocalFileStorage:
    return LocalFileStorage(
        Path("data/uploads")
    )
