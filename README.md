# yaml2helm

Convert Kubernetes YAML manifests into Helm charts automatically.

## Features

- **Multiple input formats**: File, directory, stdin, or Kustomize with multi-document YAML support
- **Smart value extraction**: Automatically extracts common fields (image, replicas, resources, etc.)
- **Resource-scoped values**: Zero conflicts by organizing values per resource
- **CRD support**: Separate CRDs into crds/ directory per Helm best practices
- **Namespace handling**: Template namespaces or preserve originals
- **Name templating**: Preserve original names or add release name prefix
- **Deterministic output**: Stable ordering and idempotent reruns
- **JSON Schema generation**: Optional values.schema.json for validation
- **Helm integration**: Built-in helm lint and helm template validation
- **Kustomize support**: Direct integration with kustomize build
- **Makefile generation**: Optional Makefile with helm workflow targets
- **Enhanced helpers**: Comprehensive _helpers.tpl with apiVersion helpers
- **Comprehensive reporting**: Track conversions with detailed statistics

## Installation

```bash
pip install -e .
```

For development:
```bash
pip install -e ".[dev]"
```

## Usage

### Basic conversion

```bash
yaml2helm --name myapp --in ./manifests --out ./charts
```

### From stdin

```bash
kubectl get deployment nginx -o yaml | yaml2helm --name nginx --out ./charts
```

### From Kustomize

```bash
yaml2helm --name myapp --kustomize ./overlays/production --out ./charts
```

### With Makefile generation

```bash
yaml2helm --name myapp --in ./manifests --out ./charts --makefile
```

This creates a `Makefile.helm` with targets for building and managing your Helm chart:

```bash
make -f Makefile.helm help      # Show available targets
make -f Makefile.helm helm      # Generate chart
make -f Makefile.helm helm-lint # Lint the chart
```

### With CRD separation

```bash
yaml2helm --name myapp --in ./manifests --out ./charts --crd-dir
```

This places CustomResourceDefinitions in `crds/` directory per Helm best practices.

### Preserve original namespaces

```bash
yaml2helm --name myapp --in ./manifests --out ./charts --preserve-ns
```

Keeps original namespaces instead of templating to `{{ .Release.Namespace }}`.

### Add release name prefix

```bash
yaml2helm --name myapp --in ./manifests --out ./charts --prefix-release-name
```

Prefixes resource names with `{{ include "myapp.fullname" . }}`.

### Advanced options

```bash
yaml2helm \
  --name myapp \
  --in ./manifests \
  --out ./charts \
  --resource-scoped \
  --crd-dir \
  --preserve-ns \
  --schema \
  --strict \
  --makefile
```

## CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--name, -n` | Chart name (required) | - |
| `--in, -i` | Input file/directory (stdin if omitted) | stdin |
| `--kustomize, -k` | Run kustomize build on directory | - |
| `--out, -o` | Output directory | `./charts` |
| `--resource-scoped/--field-scoped` | Scope values to resources (recommended) | `true` |
| `--crd-dir` | Place CRDs in separate crds/ directory | `false` |
| `--preserve-ns` | Preserve original namespaces (don't template) | `false` |
| `--original-name/--prefix-release-name` | Preserve names or add release prefix | `true` |
| `--include-cluster` | Include cluster-specific fields | `false` |
| `--schema/--no-schema` | Generate values.schema.json | `true` |
| `--lint/--no-lint` | Run helm lint | `true` |
| `--template/--no-template` | Run helm template | `true` |
| `--strict` | Fail on helm errors | `false` |
| `--makefile` | Generate Makefile.helm | `false` |

## Output Structure

```
charts/
└── myapp/
    ├── Chart.yaml
    ├── values.yaml
    ├── values.schema.json
    ├── README.md
    ├── .helmignore
    └── templates/
        ├── _helpers.tpl
        ├── NOTES.txt
        ├── 01-deployment-nginx.yaml
        └── 02-service-nginx.yaml
```

## Extracted Values

yaml2helm automatically extracts and templates:

- **Image**: repository and tag
- **Replicas**: for Deployments, StatefulSets
- **Resources**: CPU/memory limits and requests
- **Service**: type and ports
- **Ingress**: rules and TLS
- **Environment variables**: from containers
- **Node affinity**: nodeSelector, tolerations, affinity
- **HPA**: min/max replicas and target CPU

## Examples

### Convert a deployment

```bash
# Input: deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: nginx
        image: nginx:1.19

# Run conversion
yaml2helm --name nginx --in deployment.yaml --out ./charts

# Output: charts/nginx/values.yaml
image:
  repository: nginx
  tag: "1.19"
replicas: 3

# Output: charts/nginx/templates/01-deployment-nginx.yaml (templated)
spec:
  replicas: {{ .Values.replicas }}
  template:
    spec:
      containers:
      - image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
```

### Multi-document YAML

```bash
# Input file with multiple resources separated by ---
yaml2helm --name myapp --in multi.yaml --out ./charts
```

### Directory of manifests

```bash
# Convert all YAML files in a directory
yaml2helm --name myapp --in ./k8s-manifests --out ./charts
```

## Testing

Run tests:
```bash
pytest tests/ -v
```

With coverage:
```bash
pytest tests/ --cov=yaml2helm --cov-report=term-missing
```

## Algorithm

1. **Discovery**: Find YAML files, split multi-docs, parse with ruamel.yaml
2. **Validation**: Check for apiVersion, kind, metadata.name
3. **Normalization**: Sort maps and lists for deterministic output
4. **Extraction**: Extract values per heuristics, replace with Helm templates
5. **Writing**: Generate template files as `NN-<kind>-<name>.yaml`
6. **Schema**: Create values.schema.json from extracted values
7. **Validation**: Run helm lint and helm template if available

## Requirements

- Python 3.11+
- Optional: helm CLI for validation

## Dependencies

- typer: CLI framework
- ruamel.yaml: YAML parsing with comments preservation
- jinja2: Template rendering
- jsonschema: Schema validation
- rich: Terminal formatting

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=yaml2helm

# Test with helm integration
yaml2helm --name demo --in tests/data/input --out /tmp/charts
helm lint /tmp/charts/demo
helm template test /tmp/charts/demo
```

## License

MIT
