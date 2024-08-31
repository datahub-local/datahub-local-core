#!/bin/sh

SERVICE_ACCOUNT_DIR="/var/run/secrets/kubernetes.io/serviceaccount"
KUBERNETES_SERVICE_SCHEME=$(case $KUBERNETES_SERVICE_PORT in 80|8080|8081) echo "http";; *) echo "https"; esac)
KUBERNETES_SERVER_URL="$KUBERNETES_SERVICE_SCHEME"://"$KUBERNETES_SERVICE_HOST":"$KUBERNETES_SERVICE_PORT"
KUBERNETES_CLUSTER_CA_FILE="$SERVICE_ACCOUNT_DIR"/ca.crt
KUBERNETES_NAMESPACE=$(cat "$SERVICE_ACCOUNT_DIR"/namespace)
KUBERNETES_USER_TOKEN=$(cat "$SERVICE_ACCOUNT_DIR"/token)
KUBERNETES_CONTEXT="main"

KUBE_CONFIG="${1:-$HOME/.kube/config}"
KUBE_CONFIG_DIR="$(dirname $KUBE_CONFIG)"

mkdir -p "$KUBE_CONFIG_DIR"

cat << EOF > "$KUBE_CONFIG"
apiVersion: v1
kind: Config
preferences: {}
current-context: $KUBERNETES_CONTEXT
clusters:
- cluster:
    server: $KUBERNETES_SERVER_URL
    certificate-authority: $KUBERNETES_CLUSTER_CA_FILE
  name: $KUBERNETES_CONTEXT
users:
- name: podServiceAccount
  user:
    token: $KUBERNETES_USER_TOKEN
contexts:
- context:
    cluster: $KUBERNETES_CONTEXT
    user: podServiceAccount
    namespace: $KUBERNETES_NAMESPACE
  name: $KUBERNETES_CONTEXT
EOF

if [ $? -eq 0 ]; then
    echo "Created $KUBE_CONFIG"
else
    echo "Error creating $KUBE_CONFIG"
    exit 1
fi