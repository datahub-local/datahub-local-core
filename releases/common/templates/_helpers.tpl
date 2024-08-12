{{- define "kubeconfigCreatorName" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" $name "kubeconfig-creator" | trunc 63 | trimSuffix "-" }}
{{- end }}