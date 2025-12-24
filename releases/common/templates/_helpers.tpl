{{- define "name" -}}
{{ default .Chart.Name .Values.nameOverride }}
{{- end }}

{{- define "kubeconfigCreatorName" -}}
{{- $name := (include "name" .) }}
{{- printf "%s-%s" $name "kubeconfig-creator" | trunc 63 | trimSuffix "-" }}
{{- end }}