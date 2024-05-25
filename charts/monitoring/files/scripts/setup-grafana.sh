#!/bin/bash

# Set the dashboard as the homepage
set_homepage() {
  if [ -z "${GRAFANA_URL}" ]; then
    echo "Failed to retrieve Grafana Url"
    exit 1
  fi

  if [ -z "${HOMEPAGE_DASHBOARD_UID}" ]; then
    echo "Failed to retrieve dashboard UID"
    exit 1
  fi

  curl -X PATCH "${GRAFANA_URL}/api/org/preferences" \
       -H "Content-Type: application/json" \
       -d "{
             \"homeDashboardUid\": \"${HOMEPAGE_DASHBOARD_UID}\"
           }"
}

# Main function
main() {
  set_homepage
}

# Execute the script
main