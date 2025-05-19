#!/bin/sh

N8N_NODE_MODULES_PATH=/usr/local/lib/node_modules/n8n/node_modules

if [ -n "$CUSTOM_EXTERNAL_MODULES" ]; then
  for lib in $(echo "$CUSTOM_EXTERNAL_MODULES" | sed "s/,/ /g"); do
    echo "Installing external library: $lib"

    npm i --prefix "$N8N_NODE_MODULES_PATH" "$lib" || echo "Error Installing external library: $lib"
  done
fi

sh /docker-entrypoint.sh "$@"
