#!/bin/sh

N8N_NODE_MODULES_PATH=$HOME/node_modules

if [ -n "$CUSTOM_EXTRA_MODULES" ]; then
  for lib in $(echo "$CUSTOM_EXTRA_MODULES" | sed "s/,/ /g"); do
    echo "Installing extra library: $lib"

    npm i "$lib" || echo "Error Installing extra library: $lib"
  done
fi

if [ -n "$CUSTOM_COMMUNITY_NODES" ]; then
  for lib in $(echo "$CUSTOM_COMMUNITY_NODES" | sed "s/,/ /g"); do
    echo "Installing community node: $lib"

    npm i "$lib" || echo "Error Installing community node: $lib"
  done
fi

sh /docker-entrypoint.sh "$@"
