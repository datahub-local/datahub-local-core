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
      namespace: argocd
    spec:
      project: default
      source:
        repoURL: https://github.com/datahub-local/datahub-local-core.git
        targetRevision: main
        path: .
      destination:
        server: "https://kubernetes.default.svc"
      syncPolicy:
        automated: {}
        syncOptions:
          - ServerSideApply=true
    EOF
    ```

2. Wait until the Application is deployed.

### Debugging

For debugging purposes, you can deploy the repository against a local cluster. For create it run:

1. Create a local K8s cluster.

    ```bash
    k3d cluster create -p "8443:443@loadbalancer" --agents 2
    ```

2. Deploy ArgoCD.

    ```bash
    cat > /tmp/atgocd.values.yaml <<EOF
    configs:
      params:
        server.insecure: true
        application.namespaces: "default,argocd"
        server.disable.auth: true
      cmp:
        create: true
        plugins:
          helmfile:
            allowConcurrency: true
            discover:
              fileName: helmfile.yaml*
            generate:
              command:
                - bash
                - "-c"
                - |
                  PARAMS=()
  
                  if [[ -v ARGOCD_APP_NAMESPACE ]]; then
                    PARAMS+=(-n \$ARGOCD_APP_NAMESPACE)
                  fi
  
                  if [[ -v ENV_NAME ]]; then
                    PARAMS+=(-e \$ENV_NAME)
                  elif [[ -v ARGOCD_ENV_ENV_NAME ]]; then
                    PARAMS+=(-e \$ARGOCD_ENV_ENV_NAME)
                  fi
                  
                  PARAMS+=(template --include-crds -q)
                  
                  helmfile "\${PARAMS[@]}"
            lockRepo: false
    repoServer:
      clusterRoleRules:
        enabled: true
      extraContainers:
        - name: helmfile
          image: ghcr.io/helmfile/helmfile:v0.163.1
          command: ["/var/run/argocd/argocd-cmp-server"]
          env:
            - name: HELM_CACHE_HOME
              value: /tmp/helm/cache
            - name: HELM_CONFIG_HOME
              value: /tmp/helm/config
            - name: HELMFILE_CACHE_HOME
              value: /tmp/helmfile/cache
            - name: HELMFILE_TEMPDIR
              value: /tmp/helmfile/tmp
          securityContext:
            runAsNonRoot: true
            runAsUser: 999
          volumeMounts:
            - mountPath: /var/run/argocd
              name: var-files
            - mountPath: /home/argocd/cmp-server/plugins
              name: plugins
            - mountPath: /home/argocd/cmp-server/config/plugin.yaml
              subPath: helmfile.yaml
              name: argocd-cmp-cm
            - mountPath: /tmp
              name: helmfile-tmp
      volumes:
        - name: argocd-cmp-cm
          configMap:
            name: argocd-cmp-cm
        - name: helmfile-tmp
          emptyDir: {}
    EOF

    helm repo add argo https://argoproj.github.io/argo-helm
    helm install -n argocd --create-namespace argo-cd argo/argo-cd --version 6.7.17 --values /tmp/atgocd.values.yaml
    ```

3. Forward ArgoCD port and access [ArgoCD UI](http://localhost:8080).

    ```bash
    kubectl port-forward svc/argo-cd-argocd-server -n argocd 8080:80
    ```

4. Create an ArgoCD Application

    ```bash
    kubectl apply -f - <<EOF
    kind: AppProject
    apiVersion: argoproj.io/v1alpha1
    metadata:
      name: "namespace-argocd"
    spec:
      clusterResourceWhitelist:
        - group: "*"
          kind: "*"
      destinations:
        - namespace: "*"
          server: "*"
      sourceNamespaces:
        - "argocd"
      sourceRepos:
        - "*"
    EOF
    ```

5. [Create](#usage) a Application for the repo.

6. Delete k8s cluster.

    ```bash
    k3d cluster delete
    ```
