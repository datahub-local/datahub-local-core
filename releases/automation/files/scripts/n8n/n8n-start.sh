#!/bin/sh

N8N_NODE_MODULES_PATH=/usr/local/lib/node_modules/n8n
NODE_USER=node

npm -g install pnpm

if [ -n "$CUSTOM_EXTRA_MODULES" ]; then
  cd $N8N_NODE_MODULES_PATH
  for lib in $(echo "$CUSTOM_EXTRA_MODULES" | sed "s/,/ /g"); do
    echo "Installing extra library: $lib"

    pnpm add "$lib" || echo "Error Installing extra library: $lib"
  done
fi

if [ -n "$CUSTOM_COMMUNITY_NODES" ]; then  
  for lib in $(echo "$CUSTOM_COMMUNITY_NODES" | sed "s/,/ /g"); do
    echo "Installing community node: $lib"
    su $NODE_USER -c "cd && pnpm install $lib" || echo "Error Installing community node: $lib"
  done
fi

CMD="sh /docker-entrypoint.sh $@"
su $NODE_USER -c "$CMD"