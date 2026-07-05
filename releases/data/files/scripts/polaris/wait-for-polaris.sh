until curl -s -o /dev/null "$POLARIS_URL/api/management/v1/catalogs"; do
  echo "Waiting for Polaris to be ready..."; sleep 5
done
echo "Polaris is ready"
