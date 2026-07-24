run_sql() {
  trino --server "$TRINO_SERVER" --user "$TRINO_USER" --execute "$1"
}

echo "Waiting for Trino coordinator at ${TRINO_SERVER}..."
until run_sql "SELECT 1" >/dev/null 2>&1; do
  echo "Waiting for Trino coordinator..."
  sleep 10
done

# CREATE SCHEMA IF NOT EXISTS is idempotent; the Polaris catalog must already
# exist (created by the bootstrap job) for the REST catalog call to succeed.
for CATALOG in $CATALOGS; do
  echo "Creating schema ${CATALOG}.main..."
  run_sql "CREATE SCHEMA IF NOT EXISTS ${CATALOG}.main WITH (location = 's3://datahub-local-${CATALOG}')" || true
done

echo "Iceberg schema creation complete."
