# DataHub.local - Core

Helmfile project for deploying core services of [**DataHub.local**](https://datahub-local.alvsanand.com/) via [ArgoCD](https://argo-cd.readthedocs.io/en/stable/)

## Usage

1. Create an ArgoCD Application

    ```bash
    kubectl apply -f - <<EOF
    apiVersion: argoproj.io/v1alpha1
    kind: Application
    metadata:
        name: datahub-local-core
    spec:
        source:
            repoURL: https://github.com/datahub-local/datahub-local-core.git
            targetRevision: main
            path: .
        destination:
            server: 'https://kubernetes.default.svc'
        syncPolicy:
            automated:
                prune: true
                selfHeal: true
            syncOptions:
                - CreateNamespace=true
            retry:
                limit: 2
    EOF
    ```

2. Wait until the Application is deployed.

### Debugging

For debugging purposes, you can run the run against a local cluster. For that run:

1. Create a local K8s cluster.

    ```bash
    k3d cluster create -p "8443:443@loadbalancer" --agents 2
    ```

2. Deploy ArgoCD.

    ```bash
    kubectl create namespace argocd
    kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
    ```

3. Forward ArgoCD port using "admin" and the generated password.

    ```bash
    echo "#############################"
    echo "ArgoCD PASSWORD: $(kubectl get secret -n argocd argocd-initial-admin-secret -o json | jq -r '.data.password' | base64 -d)"
    echo "#############################"

    kubectl port-forward svc/argocd-server -n argocd 8080:443
    ```

4. Access [ArgoCD UI](https://localhost:8080).
