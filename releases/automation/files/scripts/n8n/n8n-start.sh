    #!/bin/sh
    
    N8N_NODE_MODULES_PATH=/usr/local/lib/node_modules/n8n
    NODE_USER=node
    
    if [ -n "$CUSTOM_EXTRA_MODULES" ]; then
      cd $N8N_NODE_MODULES_PATH
    
      CUSTOM_EXTRA_MODULES=$(echo "$CUSTOM_EXTRA_MODULES" | sed "s/,/ /g")
      echo "Installing extra modules: $CUSTOM_EXTRA_MODULES"
    
      npm add "$CUSTOM_EXTRA_MODULES" || echo "Error Installing extra modules: $CUSTOM_EXTRA_MODULES"
    fi
    
    if [ -n "$CUSTOM_COMMUNITY_NODES" ]; then
      CUSTOM_COMMUNITY_NODES=$(echo "$CUSTOM_COMMUNITY_NODES" | sed "s/,/ /g")
      echo "Installing community nodes: $CUSTOM_COMMUNITY_NODES"
      su $NODE_USER -c "cd && npm install $CUSTOM_COMMUNITY_NODES" || echo "Error Installing community nodes: $CUSTOM_COMMUNITY_NODES"
    fi
    
    CMD="sh /docker-entrypoint.sh $@"
    su $NODE_USER -c "$CMD"