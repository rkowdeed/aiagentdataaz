import csv
import json
from pathlib import Path
from typing import Any

from mock_s3 import MockS3Bucket, S3Object

class ExplorerAgent:
    def discover(self, bucket: MockS3Bucket) -> list[S3Object]:
        return bucket.list_objects()

    def summarize(self, objects: list[S3Object]) -> list[dict[str, Any]]:
        return [
            {
                "key": obj.key,
                "size": obj.size,
                "last_modified": obj.last_modified,
            }
            for obj in objects
        ]

class CleanserAgent:
    required_headers = [
        "lot_id",
        "operation_step",
        "equipment_id",
        "process_date",
        "status",
        "quantity",
        "yield_pct",
        "metadata",
    ]
    metadata_schema_path = Path(__file__).resolve().parent / "metadata_field_types.txt"
    metadata_schema: dict[str, str] | None = None

    @classmethod
    def _load_metadata_schema(cls) -> dict[str, str]:
        if cls.metadata_schema is not None:
            return cls.metadata_schema

        schema: dict[str, str] = {}
        if not cls.metadata_schema_path.exists():
            cls.metadata_schema = schema
            return schema

        with open(cls.metadata_schema_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" not in line:
                    continue
                field_name, data_type = [part.strip() for part in line.split(":", 1)]
                schema[field_name] = data_type.lower()

        cls.metadata_schema = schema
        return schema

    def validate(self, bucket: MockS3Bucket, obj: S3Object) -> dict[str, Any]:
        metadata_schema = self._load_metadata_schema()
        text = bucket.read_file(obj.key)
        reader = csv.DictReader(text.splitlines())
        issues: list[str] = []

        if reader.fieldnames is None:
            issues.append("CSV file has no header row.")
            return {"ok": False, "issues": issues, "rows": []}

        missing = [h for h in self.required_headers if h not in reader.fieldnames]
        if missing:
            issues.append(f"Missing required headers: {', '.join(missing)}")

        rows = []
        row_count = 0
        for line_number, row in enumerate(reader, start=2):
            row_count += 1
            if any(value is None or value == "" for value in row.values()):
                issues.append(f"Empty value found at line {line_number}.")
                continue
            # Robust parsing for quantity and yield_pct with clearer errors.
            quantity_raw = row.get("quantity")
            yield_raw = row.get("yield_pct")

            try:
                if quantity_raw is None:
                    raise ValueError("quantity is missing")
                # Allow numeric strings like "95.0" but require integer value.
                if isinstance(quantity_raw, str) and "." in quantity_raw:
                    qf = float(quantity_raw)
                    if qf.is_integer():
                        quantity = int(qf)
                    else:
                        raise ValueError(f"quantity not an integer: {quantity_raw}")
                else:
                    quantity = int(quantity_raw)
            except (ValueError, TypeError) as exc:
                issues.append(f"Type error in line {line_number} for 'quantity': {exc}")
                continue

            try:
                if yield_raw is None or yield_raw == "":
                    raise ValueError("yield_pct is missing or empty")
                yield_pct = float(yield_raw)
            except (ValueError, TypeError) as exc:
                issues.append(f"Type error in line {line_number} for 'yield_pct': {exc}")
                continue

            try:
                metadata = json.loads(row["metadata"])
                if not isinstance(metadata, dict):
                    raise ValueError("metadata must be a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                issues.append(f"Invalid metadata JSON at line {line_number}: {exc}")
                continue

            issues.extend(self._validate_metadata(metadata, line_number, metadata_schema))
            if any(issue.startswith("Invalid metadata") or issue.startswith("Missing metadata") for issue in issues):
                continue

            rows.append(
                (
                    row["lot_id"].strip(),
                    row["operation_step"].strip(),
                    row["equipment_id"].strip(),
                    row["process_date"].strip(),
                    row["status"].strip(),
                    quantity,
                    yield_pct,
                    json.dumps(metadata, separators=(",", ":"), sort_keys=True),
                )
            )

        if row_count == 0:
            issues.append("No data rows found in file.")

        return {"ok": len(issues) == 0, "issues": issues, "rows": rows}

    def _validate_metadata(self, metadata: dict[str, Any], line_number: int, schema: dict[str, str]) -> list[str]:
        issues: list[str] = []
        for field_name, expected_type in schema.items():
            value, found = self._resolve_field(metadata, field_name)
            if not found:
                issues.append(f"Missing metadata field '{field_name}' at line {line_number}.")
                continue

            if expected_type == "integer":
                if not (isinstance(value, int) and not isinstance(value, bool)):
                    issues.append(f"Invalid metadata field '{field_name}' at line {line_number}: expected integer, got {type(value).__name__}")
            elif expected_type == "decimal":
                if not (isinstance(value, (int, float)) and not isinstance(value, bool)):
                    issues.append(f"Invalid metadata field '{field_name}' at line {line_number}: expected decimal, got {type(value).__name__}")
            elif expected_type == "char":
                if not isinstance(value, str):
                    issues.append(f"Invalid metadata field '{field_name}' at line {line_number}: expected char, got {type(value).__name__}")
            elif expected_type == "boolean":
                if not isinstance(value, bool):
                    issues.append(f"Invalid metadata field '{field_name}' at line {line_number}: expected boolean, got {type(value).__name__}")
            else:
                issues.append(f"Unknown metadata type '{expected_type}' for field '{field_name}' at line {line_number}.")
        return issues

    def _resolve_field(self, data: dict[str, Any], field_name: str) -> tuple[Any, bool]:
        current: Any = data
        for part in field_name.split('.'):
            if not isinstance(current, dict) or part not in current:
                return None, False
            current = current[part]
        return current, True

class LoaderAgent:
    def load(self, db: Any, bucket: MockS3Bucket, obj: S3Object, rows: list[tuple]) -> dict[str, Any]:
        ingest_id = db.insert_ingest_summary(
            file_name=obj.key.split("/")[-1],
            s3_key=obj.key,
            file_hash=bucket.compute_hash(obj.key),
            record_count=len(rows),
            status="loaded",
        )
        db.insert_operation_rows(ingest_id, [(ingest_id, *row) for row in rows])
        return {"ingest_id": ingest_id, "row_count": len(rows)}
