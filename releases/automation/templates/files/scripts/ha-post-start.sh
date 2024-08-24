#!/bin/bash

SCRIPT_NAME=${0##*/}
exec > >(tee /tmp/$SCRIPT_NAME.log) 2>&1
set -e

########################################
CONFIG_DIR=/config
ADMIN_USER=${ADMIN_USER:-admin}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin}
########################################

HA_URL="http://127.0.0.1:8123"
CLIENT_ID="$HA_URL"

cd $CONFIG_DIR

echo "Init $SCRIPT_NAME"

if [ ! -f .storage/.intialized ]; then
  REQUEST='{
    "client_id": "'$CLIENT_ID'",
    "name": "'$ADMIN_USER'",
    "username": "'$ADMIN_USER'",
    "password": "'$ADMIN_PASSWORD'",
    "language": "en-GB"
  }'

  sleep 10

  echo "Creating user"

  RESPONSE=$(curl -Ss "$HA_URL/api/onboarding/users" \
    --header "Content-Type: application/json" \
    -X POST \
    --data "$REQUEST")
  
  AUTH_CODE=$(echo "$RESPONSE" | jq -r '.auth_code')

  sleep 1

  echo "Getting token"

  RESPONSE=$(curl -Ss "$HA_URL/auth/token" -X POST \
    -d "client_id=$CLIENT_ID&code=$AUTH_CODE&grant_type=authorization_code")
  
  ACCESS_TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')

  sleep 1

  echo "Executing onboarding/core_config"

  curl -Ss "$HA_URL/api/onboarding/core_config" -X POST \
    --header "Authorization: Bearer $ACCESS_TOKEN"

  sleep 1

  echo "Executing onboarding/analytics"

  curl -Ss "$HA_URL/api/onboarding/analytics" -X POST \
    --header "Authorization: Bearer $ACCESS_TOKEN"

  sleep 1

  REQUEST='{
    "client_id": "'$CLIENT_ID'",
    "redirect_uri": "'$CLIENT_ID'"
  }'

  echo "Executing onboarding/integration"

  curl -Ss "$HA_URL/api/onboarding/integration" \
    --header "Content-Type: application/json" \
    --header "Authorization: Bearer $ACCESS_TOKEN" \
    -X POST \
    --data "$REQUEST"

  sleep 1

  ADMIN_ID=$(cat .storage/auth | jq -r '.data.users[] | select(.name == "'$ADMIN_USER'") | .id')
  
  cat auth_providers.final.yaml.tpl | sed 's/ADMIN_ID/'$ADMIN_ID'/g' > auth_providers.yaml

  echo "Created auth_providers.yaml" && cat auth_providers.yaml

  echo "DONE" > .storage/.intialized

  echo "Rebooting"

  curl -Ss "$HA_URL/api/services/homeassistant/restart" -X POST \
    --header "Authorization: Bearer $ACCESS_TOKEN"
else
  echo "Home Assistant already initialized"
fi

echo "Finish $SCRIPT_NAME"
