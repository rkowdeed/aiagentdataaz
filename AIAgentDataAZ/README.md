# AIAGENTDATAAZ

This project implements a simple local data ingestion pipeline for semiconductor operations using:
- local mock S3 storage (`mock_s3_bucket/`)
- local SQLite database (`data/semiconductor.db`)
- AI-style agents: `ExplorerAgent`, `CleanserAgent`, and `LoaderAgent`

## How it works

1. `ExplorerAgent` scans the mock S3 bucket for files.
2. `CleanserAgent` validates file contents and checks metadata.
3. `LoaderAgent` writes validated records into SQLite tables.
4. The pipeline detects new or updated files by hash and processes them.

## Run

```powershell
python main.py
```

Then add or update files in `mock_s3_bucket/`.

## Data model

- `file_ingest`: tracks ingest history and validation status.
- `semiconductor_operation`: stores semiconductor operation rows, including a nested JSON `metadata` field.

### Table relationship

- `file_ingest` is the parent table.
- `semiconductor_operation` is the child table.
- `semiconductor_operation.file_ingest_id` references `file_ingest.id`.

## Metadata schema

The project uses `metadata_field_types.txt` to define expected nested metadata fields and types.
Supported types include:
- `integer`
- `decimal`
- `char`
- `boolean`

Example valid metadata JSON:

```json
{
  "execution_time_ms": 120,
  "process_specification": {
    "name": "etch-A",
    "version": "1.0"
  },
  "equipment_conditions": {
    "temperature": {
      "setpoint": 20,
      "unit": "C"
    },
    "pressure": "1atm",
    "active": true
  }
}
```

The sample valid CSV includes metadata like `execution_time_ms`, `process_specification.name`, `process_specification.version`, and `equipment_conditions.active`.
Invalid rows are used to test type validation, such as invalid numeric values and malformed boolean metadata.

## Sample data

The repository seeds two files automatically:
- `semiconductor_operations_20260623.csv` (valid)
- `semiconductor_operations_20260624_invalid.csv` (invalid)

## Notes
- No AWS dependencies are required.
- The mock S3 bucket is just a local folder with file metadata.
- SQLite is used as the target database.

## Key Design:

No framework dependencies — Just Python classes with methods
Data flows as method returns — Each agent returns results (dictionaries/tuples) that feed into the next stage
Polling loop — main.py:95-103 runs continuous polling (5-second intervals) to check for new/changed files
State tracking — processed_state.json stores file hashes to skip unchanged files
This is a linear pipeline, not a graph—perfect for simple ETL workflows. No need for LangGraph unless you need:

Conditional branching/loops
Parallel execution
Complex state management
Agent communication/routing