OUTPUT=$(java -jar /deployments/polaris-admin-tool.jar bootstrap \
  -r default-realm \
  -c "default-realm,root,${POLARIS_CLIENT_SECRET}" 2>&1)
EXIT_CODE=$?
echo "$OUTPUT"
if echo "$OUTPUT" | grep -q "already been bootstrapped"; then
  echo "Realm already bootstrapped, skipping."
  exit 0
fi
exit $EXIT_CODE
