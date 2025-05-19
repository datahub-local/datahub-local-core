#!/bin/sh

if [ -n "$NODE_FUNCTION_ALLOW_EXTERNAL" ]; then
  for lib in $(echo "$NODE_FUNCTION_ALLOW_EXTERNAL" | sed "s/,/ /g"); do
    echo "Installing external library: $lib"

    npm i "$lib" || echo "Error Installing external library: $lib"
  done
fi

sh /docker-entrypoint.sh "$@"
