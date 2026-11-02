# ./data

Put the assessment inputs here before `docker compose up`. They are mounted into the API container at
`/app/data` and are not committed to this repository:

```
data/
  corpus/          # the HR documents (PDF, DOCX, Markdown, HTML)
  manifest.json    # metadata for every document
  veltrix.db       # SQLite database of employees and leave
```

The paths come from `CORPUS_DIR`, `MANIFEST_PATH` and `DB_PATH` (see `.env.example`). Ingestion runs
automatically at start-up; `GET /health` returns 200 when it has finished. The automated tests do not use
this folder: they build their own synthetic corpus and database.
