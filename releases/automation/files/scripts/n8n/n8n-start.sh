    #!/bin/sh
    
    NODE_USER=node
    
    if [ -n "$CUSTOM_EXTRA_MODULES" ]; then
      CUSTOM_EXTRA_MODULES=$(echo "$CUSTOM_EXTRA_MODULES" | sed "s/,/ /g")
      echo "Installing extra modules: $CUSTOM_EXTRA_MODULES"
    
      # npm add inside the n8n package tree fails on this image (npm's arborist
      # reads a null package name), so install globally: the module lands in
      # /usr/local/lib/node_modules and its binaries are runnable by path.
      npm install -g "$CUSTOM_EXTRA_MODULES" || echo "Error Installing extra modules: $CUSTOM_EXTRA_MODULES"
    fi
    
    if [ -n "$CUSTOM_COMMUNITY_NODES" ]; then
      CUSTOM_COMMUNITY_NODES=$(echo "$CUSTOM_COMMUNITY_NODES" | sed "s/,/ /g")
      echo "Installing community nodes: $CUSTOM_COMMUNITY_NODES"
      # --ignore-scripts: the image has no python/gcc, so the isolated-vm pulled in
      # by the n8n-workflow peer dep cannot build and would fail the whole install.
      su $NODE_USER -c "export PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true && cd && npx npm@9 install --ignore-scripts $CUSTOM_COMMUNITY_NODES" || echo "Error Installing community nodes: $CUSTOM_COMMUNITY_NODES"
    fi
    
    CMD="sh /docker-entrypoint.sh $@"
    su $NODE_USER -c "$CMD"