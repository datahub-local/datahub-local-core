# NanoClaw live PoC

Proves one path: host → Kubernetes Pod running NanoClaw's agent container → LiteLLM → reply written
to `outbound.db`. It does not install channels, approvals, or the release from
`releases/automation/`.

## Preconditions

- `nanoclaw-host:poc` and `nanoclaw-agent:poc` imported into the containerd store of
  `datahublocal-amd-1` (the pinned node).
- A `litellm-key` Secret in `spike-nanoclaw`, copied from `data/litellm-auth-credentials` (`API_KEY`).
- The fork's driver registered through `src/drivers/installed.ts` and the `litellm-proxy` gateway
  through `src/gateway-providers/installed.ts` (see `nanoclaw-poc.patch`).

## Build and import

```bash
cd <nanoclaw-fork>
docker build -f Dockerfile.poc -t nanoclaw-host:poc .
docker build -t nanoclaw-agent:poc container
docker pull node:22-slim   # proxy image, multi-arch

docker save nanoclaw-host:poc nanoclaw-agent:poc node:22-slim \
  | ssh ripenses@192.168.31.104 'sudo k3s ctr images import -'
```

## Apply

```bash
kubectl apply -f spike.yaml
kubectl -n spike-nanoclaw create configmap litellm-proxy \
  --from-file=litellm-proxy.js --dry-run=client -o yaml | kubectl apply -f -
KEY=$(kubectl -n data get secret litellm-auth-credentials -o jsonpath='{.data.API_KEY}' | base64 -d)
kubectl -n spike-nanoclaw create secret generic litellm-key \
  --from-literal=litellm-key="$KEY" --dry-run=client -o yaml | kubectl apply -f -
```

The Job in `spike.yaml` is a placeholder; re-apply it after importing the images:

```bash
kubectl -n spike-nanoclaw delete job nanoclaw-poc-host --ignore-not-found
kubectl apply -f spike.yaml
kubectl -n spike-nanoclaw wait --for=condition=complete job/nanoclaw-poc-host --timeout=10m
kubectl -n spike-nanoclaw logs job/nanoclaw-poc-host
```

## Expected evidence

- host log: `Session Pod created`, then `E2E works!` from `messages_out`;
- `kubectl -n spike-nanoclaw get pods` shows `ncl-…` created during the run;
- the agent Pod spec has no `x-api-key` / LiteLLM key, only the proxy URL and `placeholder`;
- the proxy's upstream request is visible in LiteLLM logs or the proxy's stdout.

## Teardown

```bash
kubectl delete namespace spike-nanoclaw
```
