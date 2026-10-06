from pathlib import Path


class LocalFileStorage:
    def __init__(self, root: Path):
        self.root = root

    def write_chunk(
        self,
        storage_key: str,
        chunk: bytes,
    ) -> None:
        path = self.root / storage_key

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open("ab") as destination:
            destination.write(chunk)

    def delete(
        self,
        storage_key: str,
    ) -> None:
        path = self.root / storage_key

        if path.exists():
            path.unlink()
