set -e

echo "Getting Polaris admin token..."
TOKEN_RESPONSE=$(curl -s -X POST "$POLARIS_URL/api/catalog/v1/oauth/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=root&client_secret=${POLARIS_CLIENT_SECRET}&scope=PRINCIPAL_ROLE:ALL")
TOKEN=$(echo "$TOKEN_RESPONSE" | sed 's/.*"access_token":"\([^"]*\)".*/\1/')
if [ -z "$TOKEN" ] || [ "$TOKEN" = "$TOKEN_RESPONSE" ]; then
  echo "Failed to get token: $TOKEN_RESPONSE"
  exit 1
fi
echo "Token acquired"

for CATALOG in $CATALOGS; do
  echo "Creating/updating Polaris catalog: $CATALOG"
  BASE_LOCATION="s3://datahub-local-${CATALOG}"
  STORAGE_CONFIG='{"storageType":"S3","allowedLocations":["'"$BASE_LOCATION"'"],"region":"'"$S3_REGION"'","endpoint":"https://'"$S3_ENDPOINT"'","pathStyleAccess":true,"stsUnavailable":true}'
  PROPERTIES='{"default-base-location":"'"$BASE_LOCATION"'","polaris.config.drop-with-purge.enabled":"true"}'
  RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$POLARIS_URL/api/management/v1/catalogs" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"catalog":{"name":"'"$CATALOG"'","type":"INTERNAL","properties":'"$PROPERTIES"',"storageConfigInfo":'"$STORAGE_CONFIG"'}}')
  HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  if [ "$HTTP_CODE" = "201" ]; then
    echo "Catalog $CATALOG created successfully"
  elif [ "$HTTP_CODE" = "409" ]; then
    echo "Catalog $CATALOG already exists, updating storage config..."
    CATALOG_RESPONSE=$(curl -s "$POLARIS_URL/api/management/v1/catalogs/$CATALOG" \
      -H "Authorization: Bearer $TOKEN")
    ENTITY_VERSION=$(echo "$CATALOG_RESPONSE" | grep -o '"entityVersion":[0-9]*' | grep -o '[0-9]*')
    UPDATE_RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT "$POLARIS_URL/api/management/v1/catalogs/$CATALOG" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{"currentEntityVersion":'"$ENTITY_VERSION"',"properties":'"$PROPERTIES"',"storageConfigInfo":'"$STORAGE_CONFIG"'}')
    UPDATE_CODE=$(echo "$UPDATE_RESPONSE" | tail -1)
    echo "$UPDATE_CODE" | grep -qE "^(200|204)$" || echo "Warning: unexpected update response for catalog $CATALOG: $UPDATE_RESPONSE"
  else
    echo "Warning: unexpected response for catalog $CATALOG: $RESPONSE"
  fi

  # Create a catalog role with full data access and assign it to service_admin
  echo "Setting up catalog role for $CATALOG..."
  ROLE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$POLARIS_URL/api/management/v1/catalogs/$CATALOG/catalog-roles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"catalogRole":{"name":"data_admin"}}')
  ROLE_CODE=$(echo "$ROLE_RESPONSE" | tail -1)
  if [ "$ROLE_CODE" = "201" ]; then
    echo "Catalog role data_admin created for $CATALOG"
  elif [ "$ROLE_CODE" = "409" ]; then
    echo "Catalog role data_admin already exists for $CATALOG"
  else
    echo "Warning: unexpected response creating catalog role for $CATALOG: $ROLE_RESPONSE"
  fi

  GRANT_RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT "$POLARIS_URL/api/management/v1/catalogs/$CATALOG/catalog-roles/data_admin/grants" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"grant":{"type":"catalog","privilege":"CATALOG_MANAGE_CONTENT"}}')
  GRANT_CODE=$(echo "$GRANT_RESPONSE" | tail -1)
  echo "$GRANT_CODE" | grep -qE "^(200|201|204)$" || echo "Warning: unexpected response granting privilege for $CATALOG: $GRANT_RESPONSE"
  echo "Granted CATALOG_MANAGE_CONTENT to data_admin for $CATALOG"

  ASSIGN_RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT "$POLARIS_URL/api/management/v1/principal-roles/service_admin/catalog-roles/$CATALOG" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"catalogRole":{"name":"data_admin"}}')
  ASSIGN_CODE=$(echo "$ASSIGN_RESPONSE" | tail -1)
  echo "$ASSIGN_CODE" | grep -qE "^(200|201|204)$" || echo "Warning: unexpected response assigning catalog role for $CATALOG: $ASSIGN_RESPONSE"
  echo "Assigned data_admin catalog role to service_admin for $CATALOG"
done

echo "Polaris catalog setup complete."
