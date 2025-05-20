#!/bin/sh

N8N_NODE_MODULES_PATH=/usr/local/lib/node_modules/n8n/node_modules/
N8N_COMMUNITY_NODES_PATH=$HOME/node_modules

if [ -n "$CUSTOM_EXTRA_MODULES" ]; then
  cd $N8N_NODE_MODULES_PATH

  for lib in $(echo "$CUSTOM_EXTRA_MODULES" | sed "s/,/ /g"); do
    echo "Installing extra library: $lib"

    npm i "$lib" || echo "Error Installing extra library: $lib"
  done
fi

if [ -n "$CUSTOM_COMMUNITY_NODES" ]; then
  cd $N8N_COMMUNITY_NODES_PATH
  
  for lib in $(echo "$CUSTOM_COMMUNITY_NODES" | sed "s/,/ /g"); do
    echo "Installing community node: $lib"

    npm i "$lib" || echo "Error Installing community node: $lib"
  done
fi

su - node sh /docker-entrypoint.sh "$@"
