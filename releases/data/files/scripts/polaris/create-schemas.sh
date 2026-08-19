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
# The location must be a dedicated subpath, not the bucket root: namespace
# creation is gated by ALLOW_NAMESPACE_LOCATION_OVERLAP (default false, and a
# different flag from the ALLOW_TABLE_LOCATION_OVERLAP we set on the server), so
# a root location is rejected for overlapping the sibling namespaces beneath it.
FAILED=""
for CATALOG in $CATALOGS; do
  echo "Creating schema ${CATALOG}.main..."
  run_sql "CREATE SCHEMA IF NOT EXISTS ${CATALOG}.main WITH (location = 's3://datahub-local-${CATALOG}/main')" || FAILED="${FAILED} ${CATALOG}"
done

if [ -n "$FAILED" ]; then
  echo "ERROR: Iceberg schema creation failed for ${FAILED}"
  exit 1
fi

echo "Iceberg schema creation complete."
