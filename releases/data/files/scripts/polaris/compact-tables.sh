run_sql() {
  trino --server "$TRINO_SERVER" --user "$TRINO_USER" --output-format TSV --execute "$1"
}

if ! run_sql "SELECT 1" >/dev/null; then
  echo "Trino is not reachable at $TRINO_SERVER"
  exit 1
fi

for CATALOG in $CATALOGS; do
  echo "Compacting catalog ${CATALOG}..."
  for SCHEMA in $(run_sql "SHOW SCHEMAS FROM ${CATALOG}" | grep -v '^information_schema$'); do
    for TABLE in $(run_sql "SHOW TABLES FROM ${CATALOG}.${SCHEMA}"); do
      FQN="${CATALOG}.${SCHEMA}.\"${TABLE}\""
      echo "Optimizing ${FQN}"
      run_sql "ALTER TABLE ${FQN} EXECUTE optimize(file_size_threshold => '128MB')" || true
      run_sql "ALTER TABLE ${FQN} EXECUTE optimize_manifests" || true
      run_sql "ALTER TABLE ${FQN} EXECUTE expire_snapshots(retention_threshold => '7d')" || true
      run_sql "ALTER TABLE ${FQN} EXECUTE remove_orphan_files(retention_threshold => '7d')" || true
    done
  done
done

echo "Iceberg table maintenance complete."
