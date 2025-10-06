# yaml2helm Quick Start

## Installation

```bash
pip install -e .
```

## Basic Usage

### Convert a directory of manifests
```bash
yaml2helm --name myapp --in ./k8s-manifests --out ./charts
```

### Convert from stdin
```bash
kubectl get deployment myapp -o yaml | yaml2helm --name myapp --out ./charts
```

### Convert from Kustomize
```bash
yaml2helm --name myapp --kustomize ./overlays/production --out ./charts
```

### Convert a single file
```bash
yaml2helm --name myapp --in deployment.yaml --out ./charts
```

### Generate with Makefile
```bash
yaml2helm --name myapp --in ./k8s --out ./charts --makefile
```

## Common Options

```bash
# Skip helm validation (faster)
yaml2helm --name myapp --in ./k8s --out ./charts --no-lint --no-template

# Separate CRDs into crds/ directory
yaml2helm --name myapp --in ./k8s --out ./charts --crd-dir

# Preserve original namespaces
yaml2helm --name myapp --in ./k8s --out ./charts --preserve-ns

# Add release name prefix to resources
yaml2helm --name myapp --in ./k8s --out ./charts --prefix-release-name

# Use field-scoped values instead of resource-scoped (may cause conflicts)
yaml2helm --name myapp --in ./k8s --out ./charts --field-scoped

# Include cluster-specific fields in templates
yaml2helm --name myapp --in ./k8s --out ./charts --include-cluster

# Disable JSON schema generation
yaml2helm --name myapp --in ./k8s --out ./charts --no-schema

# Strict mode: fail on helm errors
yaml2helm --name myapp --in ./k8s --out ./charts --strict

# Generate Makefile for chart workflow
yaml2helm --name myapp --in ./k8s --out ./charts --makefile

# ✨ NEW: Inject standard Kubernetes labels
yaml2helm --name myapp --in ./k8s --out ./charts --inject-labels

# ✨ NEW: Add custom labels to all resources
yaml2helm --name myapp --in ./k8s --out ./charts --common-labels team=platform --common-labels env=prod

# ✨ NEW: Auto-detect and add Helm hook annotations
yaml2helm --name myapp --in ./k8s --out ./charts --detect-hooks

# ✨ NEW: Override specific values
yaml2helm --name myapp --in ./k8s --out ./charts --set nginx.replicas=5 --set nginx.image.tag=v2.0

# ✨ NEW: Customize chart metadata
yaml2helm --name myapp --in ./k8s --out ./charts \
  --description "Production-ready application" \
  --app-version "1.2.3" \
  --keywords web --keywords api

# ✨ NEW: Generate environment-specific values files
yaml2helm --name myapp --in ./k8s --out ./charts --env dev --env staging --env prod

# ✨ NEW: Disable values comments (default: enabled)
yaml2helm --name myapp --in ./k8s --out ./charts --no-values-comments

# Combine multiple features
yaml2helm --name myapp --in ./k8s --out ./charts \
  --inject-labels \
  --common-labels owner=platform-team \
  --detect-hooks \
  --set nginx.replicas=3 \
  --env dev --env prod \
  --description "My awesome app" \
  --app-version "2.0.0"
```

## Testing Your Chart

After generation, test the chart:

```bash
# Lint the chart
helm lint ./charts/myapp

# Dry-run template rendering
helm template test-release ./charts/myapp

# Install to cluster
helm install myapp ./charts/myapp

# Upgrade with custom values
helm upgrade myapp ./charts/myapp --set nginx.image.tag=v2.0
```

### Using Generated Makefile

If you used `--makefile`, you can use these convenient targets:

```bash
# Show available targets
make -f Makefile.helm help

# Generate chart
make -f Makefile.helm helm

# Lint the chart
make -f Makefile.helm helm-lint

# Dry-run template
make -f Makefile.helm helm-template

# Install to cluster
make -f Makefile.helm helm-install
```

## Example Workflow

1. Export your existing Kubernetes resources:
```bash
kubectl get deploy,svc,ingress -o yaml > manifests.yaml
```

2. Convert to Helm chart:
```bash
yaml2helm --name myapp --in manifests.yaml --out ./charts
```

3. Review generated files:
```bash
tree ./charts/myapp
```

4. Customize values.yaml:
```bash
vim ./charts/myapp/values.yaml
```

5. Install the chart:
```bash
helm install myapp ./charts/myapp
```

## Extracted Values

yaml2helm automatically extracts and templates:

| Field | Example |
|-------|---------|
| Image | `nginx:1.19` → `repository: nginx, tag: '1.19'` |
| Replicas | `3` → `replicas: 3` |
| Env vars | `LOG_LEVEL=info` → `env.LOG_LEVEL: info` |
| Resources | CPU/memory limits and requests |
| Service | Type and ports |
| Node affinity | nodeSelector, tolerations, affinity |

## Troubleshooting

### No resources found
```bash
# Check if files contain valid Kubernetes manifests
yaml2helm --name test --in ./k8s --out ./charts
# Look at the "Valid objects" count in output
```

### Helm lint warnings
```bash
# Review the generated Chart.yaml
cat ./charts/myapp/Chart.yaml

# Common issues:
# - Add description, maintainers, icon in Chart.yaml manually
```

### Value conflicts
```bash
# Check the summary for "Conflicts" count
# Review the conflicts list in output
# Different resources may have different values for same field
```

## Output Structure

```
charts/myapp/
├── Chart.yaml              # Chart metadata
├── values.yaml             # Extracted values
├── values.schema.json      # JSON Schema for validation
├── README.md              # Chart documentation
├── .helmignore            # Files to ignore
└── templates/
    ├── _helpers.tpl       # Template helpers
    ├── NOTES.txt          # Install notes
    ├── 01-deployment-*.yaml
    ├── 02-service-*.yaml
    └── ...
```

## Next Steps

1. Review and customize `values.yaml`
2. Update `Chart.yaml` with proper metadata
3. Enhance templates with conditionals if needed
4. Add tests using `helm test`
5. Package and publish: `helm package ./charts/myapp`

## Tips

- Use `--no-lint --no-template` for faster iteration during development
- Always review generated templates before deploying
- Test charts in a dev cluster first
- Version your charts properly in Chart.yaml
- Document custom values in README.md
