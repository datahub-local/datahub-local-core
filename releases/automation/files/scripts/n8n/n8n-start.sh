#!/bin/sh

N8N_NODE_MODULES_PATH=/usr/local/lib/node_modules/n8n/node_modules
N8N_COMUNITY_NODES_PATH=$HOME/.n8n/nodes

if [ -n "$CUSTOM_EXTRA_MODULES" ]; then
  for lib in $(echo "$CUSTOM_EXTRA_MODULES" | sed "s/,/ /g"); do
    echo "Installing extra library: $lib"

    npm i --prefix "$N8N_NODE_MODULES_PATH" "$lib" || echo "Error Installing extra library: $lib"
  done
fi

if [ -n "$CUSTOM_COMMUNITY_NODES" ]; then
  mkdir -p "${N8N_COMUNITY_NODES_PATH}" && cd "${N8N_COMUNITY_NODES_PATH}"

  for lib in $(echo "$CUSTOM_COMMUNITY_NODES" | sed "s/,/ /g"); do
    echo "Installing community node: $lib"

    npm i "$lib" || echo "Error Installing community node: $lib"
  done
fi

sh /docker-entrypoint.sh "$@"
