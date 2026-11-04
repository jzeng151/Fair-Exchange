"""A record store on local JSON files, for running FEX locally (#101). Same rules as DynamoRecordStore (#26):
a create fails if the record exists; an update needs the stored version and producer to match."""
import json
import os
import tempfile
from pathlib import Path

from fex.models import CompletedRecord, DeclinedRecord
from fex.records import RecordConflict


class FileRecordStore:
    """One `<record_id>.json` file per record in `directory`."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, record_id: str) -> Path:
        return self.directory / f"{record_id}.json"

    def get(self, record_id: str) -> dict | None:
        path = self._path(record_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def create(self, record: CompletedRecord | DeclinedRecord) -> None:
        if self._path(record.record_id).exists():
            raise RecordConflict(record.record_id)
        self._write(record)

    def update(self, record: CompletedRecord | DeclinedRecord, expected_version: int) -> None:
        stored = self.get(record.record_id)
        if not stored or stored.get("version") != expected_version or stored.get("producer_id") != record.producer_id:
            raise RecordConflict(record.record_id)
        self._write(record)

    def _write(self, record: CompletedRecord | DeclinedRecord) -> None:
        text = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, self._path(record.record_id))  # atomic: a reader never sees half a record
