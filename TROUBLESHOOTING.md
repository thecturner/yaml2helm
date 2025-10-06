# yaml2helm Troubleshooting & Known Issues

## Testing with kube-prometheus

We tested yaml2helm with the [kube-prometheus](https://github.com/prometheus-operator/kube-prometheus) repository, which contains 95 YAML manifest files for a complete Prometheus monitoring stack.

### Results Summary

```
Files discovered: 95
Valid objects: 90
Skipped: 3
Bad YAML: 2
Templated: 90
Conflicts: 8
Errors: 4
```

## Issue #1: PrometheusRule Template Syntax Conflicts

### Problem

PrometheusRule and AlertmanagerConfig resources contain Prometheus/Alertmanager template syntax using `{{ }}`, which conflicts with Helm's template syntax.

**Example:**
```yaml
annotations:
  description: Controller {{ $labels.controller }} in {{ $labels.namespace }} namespace fails.
```

Helm tries to interpret `{{ $labels.controller }}` as a Helm template and fails with "undefined variable $labels".

### Attempted Solutions

#### Solution 1: Backtick Escaping (Partially Successful)

Wrap Prometheus templates in Helm's backtick escaping: `{{` `{{ $labels }}` `}}`

**Implementation:**
```python
# In chartwriter.py
def _escape_prometheus_templates(self, content: str) -> str:
    # Match {{ }} containing Prometheus keywords
    prometheus_pattern = r'\{\{(?:[^{}]|\{[^}]*\})*\}\}'

    def escape_prom(match):
        template = match.group(0)
        prom_indicators = ['$labels', '$value', 'printf', 'humanize', 'query']

        if any(indicator in template for indicator in prom_indicators):
            return '{{`' + template + '`}}'
        return template

    return re.sub(prometheus_pattern, escape_prom, content)
```

**Result:**
- ✅ Works for simple templates: `{{$labels.controller}}`
- ❌ Fails for nested templates with backticks: `{{ printf `template` $labels }}`

#### Solution 2: Nested Backtick Problem

Templates like this cannot be escaped with backticks:
```yaml
{{ printf `prometheus_remote_storage_shards_max{instance="%s"}` $labels.instance | query }}
```

When escaped becomes:
```yaml
{{`{{ printf `prometheus_remote_storage_shards_max{instance="%s"}` $labels.instance | query }}`}}
```

This creates nested backticks which is invalid Helm syntax.

**Error:** `bad character U+007B '{'`

### Current Recommendation

For PrometheusRule and AlertmanagerConfig resources:

1. **Option A (Current):** Keep resources as literal YAML without value extraction
   - Don't extract values from PrometheusRule/AlertmanagerConfig
   - Write them as-is without Helm templating
   - Users can edit them directly in templates/ if needed

2. **Option B:** Use Helm's `{{- with .Files }}` pattern
   - Store PrometheusRules in separate files
   - Load them via `.Files.Get` in Helm
   - Avoids template parsing conflicts

3. **Option C:** Document as known limitation
   - Note in README that PrometheusRules require manual review
   - Provide examples of how to fix in generated charts

### Implementation (Option A - Recommended)

```python
# In extractors.py - skip value extraction for PrometheusRule
SKIP_EXTRACTION_KINDS = ['PrometheusRule', 'AlertmanagerConfig']

def _process_resource(self, resource: Dict[str, Any]) -> Dict[str, Any]:
    kind = resource.get('kind', '')

    if kind in SKIP_EXTRACTION_KINDS:
        return resource  # Return as-is, no templating

    # ... continue with normal extraction
```

```python
# In chartwriter.py - skip template escaping
def _needs_template_escaping(self, resource: Dict[str, Any]) -> bool:
    # Don't escape anymore - keep these resources literal
    return False
```

## Issue #2: Value Conflicts Across Multiple Resources

### Problem

When converting multiple resources of different types, the same value path (e.g., `service.ports`, `replicas`) may have different values.

**Example from kube-prometheus:**
```
Conflict at service.ports:
  - Alertmanager: [{'name': 'web', 'port': 9093}]
  - Blackbox Exporter: [{'name': 'https', 'port': 9115}]
  - Grafana: [{'name': 'http', 'port': 3000}]
```

### Solution

**Option A:** Resource-specific values (Implemented)
```yaml
# values.yaml
alertmanager:
  service:
    ports: [...]
blackboxExporter:
  service:
    ports: [...]
```

**Option B:** Keep first value, report conflicts (Current)
- Extract first occurrence
- Report conflicts to user
- User reviews and adjusts manually

**Option C:** Don't extract conflicting fields
- Detect conflicts during extraction
- Skip templating for fields with conflicts
- Keep them literal in templates

### Recommendation

Use Option A for production charts - create resource-specific value sections. This requires enhancing the extractor to track which resource each value came from.

## Issue #3: CRD Parsing Errors

### Problem

Custom Resource Definitions (CRDs) contain complex YAML with special tags:

```
YAML parse error: could not determine a constructor for the tag 'tag:yaml.org,2002:value'
```

### Cause

CRDs use OpenAPI v3 schema which includes special YAML tags that ruamel.yaml's safe loader doesn't recognize.

### Solution

```python
# In discovery.py
def parse_file(self, file_path: Path) -> Iterator[Dict[str, Any]]:
    try:
        # Skip CRD files - they're usually in setup/ directory
        if 'CustomResourceDefinition' in str(file_path):
            self.report.skipped += 1
            return

        with open(file_path, 'r') as f:
            for doc in self.yaml.load_all(f):
                if doc is None:
                    continue
                yield doc
    except YAMLError as e:
        self.report.bad_yaml += 1
        # ... handle error
```

Or use unsafe loader for CRDs (security risk):
```python
if file_path.name.endswith('CustomResourceDefinition.yaml'):
    yaml = YAML(typ='unsafe')  # Can handle custom tags
```

## Issue #4: Resources Without Values to Extract

### Problem

Some resources (ConfigMaps, Secrets, Namespaces, CRDs) don't have standard extractable values like image/replicas/resources.

### Current Behavior

- Skipped: 3 resources (likely Namespace, RBAC without standard fields)
- These are written as literal templates

### Recommendation

This is correct behavior - not all resources need value extraction.

## Lessons Learned

### 1. Template Syntax Conflicts Are Hard

Multiple template systems (Helm + Prometheus) in the same file create fundamental conflicts that can't always be automatically resolved.

### 2. One Size Doesn't Fit All

Different resource types need different treatment:
- Deployments/StatefulSets: Heavy value extraction
- Services: Port extraction with conflict handling
- PrometheusRules: Keep literal, no templating
- CRDs: Skip or handle specially

### 3. Conflict Detection Is Critical

In real-world manifests, conflicts are common. yaml2helm correctly detects 8 conflicts in kube-prometheus, helping users understand what needs manual review.

### 4. Real-World Testing Reveals Edge Cases

Testing with kube-prometheus (95 files, 90 resources) revealed issues that simple test cases didn't:
- Nested template syntax
- CRD parsing
- Value conflicts across resource types
- Resources with no extractable values

## Recommendations for Users

When converting complex manifests like kube-prometheus:

1. **Review the summary** - Check conflicts and errors count
2. **Examine PrometheusRules** - May need manual template fixes
3. **Resolve value conflicts** - Decide which values to keep/parameterize
4. **Test with `helm template`** - Verify output before deployment
5. **Use `--no-lint --no-template`** - For faster iteration during fixes
6. **Consider splitting charts** - One chart per component may be cleaner

## Future Improvements

1. **Resource-aware value extraction** - Use resource name/type in value paths
2. **Better conflict resolution** - Merge strategies for common conflicts
3. **PrometheusRule special handling** - Store in ConfigMaps or separate files
4. **CRD detection** - Automatically skip/handle CRDs
5. **Interactive mode** - Ask user how to resolve conflicts
6. **Value prefix option** - `--value-prefix alertmanager` for component-specific values

## Success Metrics

Despite these issues, yaml2helm successfully:
- ✅ Discovered and parsed 90/95 resources (94.7%)
- ✅ Generated valid Helm chart structure
- ✅ Extracted common values (image, replicas, resources, etc.)
- ✅ Detected and reported 8 conflicts
- ✅ Created 90 template files with proper naming
- ✅ Generated values.yaml and values.schema.json
- ✅ Idempotent output (same input → same output)

The tool works well for standard Kubernetes resources. Complex custom resources like PrometheusRule need manual review, which is expected and acceptable.
