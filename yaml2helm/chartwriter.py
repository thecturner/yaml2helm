"""Helm chart writer."""

import os
from pathlib import Path
from typing import Any, Dict, List
from ruamel.yaml import YAML
from jinja2 import Environment, PackageLoader, select_autoescape

from .report import Report
from .schema import SchemaGenerator
from .util import get_resource_identifier, normalize_dict


class ChartWriter:
    """Write Helm chart files."""

    def __init__(
        self, chart_name: str, output_dir: Path,
        enable_schema: bool = True,
        crd_dir: bool = False,
        preserve_ns: bool = False,
        original_name: bool = True,
        inject_labels: bool = False,
        common_labels: Dict[str, str] = None,
        detect_hooks: bool = False,
        values_comments: bool = True,
        description: str = None,
        app_version: str = None,
        keywords: List[str] = None
    ):
        self.chart_name = chart_name
        self.output_dir = output_dir
        self.enable_schema = enable_schema
        self.crd_dir_enabled = crd_dir
        self.preserve_ns = preserve_ns
        self.original_name = original_name
        self.inject_labels = inject_labels
        self.common_labels = common_labels or {}
        self.detect_hooks = detect_hooks
        self.values_comments = values_comments
        self.description = description or f'A Helm chart for {chart_name}'
        self.app_version = app_version or '1.0.0'
        self.keywords = keywords or []
        self.chart_dir = output_dir / chart_name
        self.templates_dir = self.chart_dir / 'templates'
        self.crds_dir = self.chart_dir / 'crds' if crd_dir else None

        # YAML writer with proper formatting
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.default_flow_style = False
        self.yaml.width = 999999  # Prevent line wrapping of long Helm templates

        # Jinja2 environment for templates
        self.jinja_env = Environment(
            loader=PackageLoader('yaml2helm', 'templates'),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

    def write_chart(
        self,
        resources: List[Dict[str, Any]],
        values: Dict[str, Any],
        report: Report
    ) -> None:
        """Write complete Helm chart.

        Args:
            resources: List of templated Kubernetes resources
            values: Extracted values dictionary
            report: Report object to update
        """
        # Create directory structure
        self._create_directories()

        # Write Chart.yaml
        self._write_chart_yaml()

        # Write values.yaml
        self._write_values_yaml(values)

        # Write values.schema.json if enabled
        if self.enable_schema:
            self._write_values_schema(values)

        # Write template files
        self._write_templates(resources, report)

        # Write helpers
        self._write_helpers()

        # Write NOTES.txt
        self._write_notes()

        # Write README.md
        self._write_readme()

        # Write .helmignore
        self._write_helmignore()

        report.chart_path = self.chart_dir

    def _create_directories(self) -> None:
        """Create chart directory structure."""
        self.chart_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        if self.crds_dir:
            self.crds_dir.mkdir(parents=True, exist_ok=True)

    def _write_chart_yaml(self) -> None:
        """Write Chart.yaml file."""
        chart_data = {
            'apiVersion': 'v2',
            'name': self.chart_name,
            'description': self.description,
            'type': 'application',
            'version': '0.1.0',
            'appVersion': self.app_version,
        }

        if self.keywords:
            chart_data['keywords'] = self.keywords

        chart_path = self.chart_dir / 'Chart.yaml'
        with open(chart_path, 'w') as f:
            self.yaml.dump(normalize_dict(chart_data), f)

    def _write_values_yaml(self, values: Dict[str, Any]) -> None:
        """Write values.yaml file.

        Args:
            values: Values dictionary
        """
        values_path = self.chart_dir / 'values.yaml'

        if self.values_comments:
            # Write with comments
            with open(values_path, 'w') as f:
                f.write("# Default values for {}\n".format(self.chart_name))
                f.write("# This is a YAML-formatted file.\n")
                f.write("# Declare variables to be passed into your templates.\n\n")
                self._write_values_with_comments(f, values, 0)
        else:
            with open(values_path, 'w') as f:
                self.yaml.dump(normalize_dict(values), f)

    def _write_values_schema(self, values: Dict[str, Any]) -> None:
        """Write values.schema.json file.

        Args:
            values: Values dictionary
        """
        schema_path = self.chart_dir / 'values.schema.json'
        generator = SchemaGenerator()
        generator.write_schema(values, str(schema_path))

    def _write_templates(self, resources: List[Dict[str, Any]], report: Report) -> None:
        """Write template files for resources.

        Args:
            resources: List of templated resources
            report: Report object to update
        """
        # Track resource counts for naming
        kind_counters: Dict[str, int] = {}

        for resource in resources:
            kind = resource.get('kind', 'unknown')
            name = resource.get('metadata', {}).get('name', 'unnamed')

            # Check if this is a CRD and crd_dir is enabled
            is_crd = kind == 'CustomResourceDefinition'
            if is_crd and self.crd_dir_enabled:
                # Write CRD to crds/ directory
                self._write_crd(resource)
                report.templated += 1
                continue

            # Get counter for this kind
            if kind not in kind_counters:
                kind_counters[kind] = 0
            kind_counters[kind] += 1

            # Generate filename: NN-kind-name.yaml
            counter = str(kind_counters[kind]).zfill(2)
            identifier = get_resource_identifier(resource)
            filename = f"{counter}-{identifier}.yaml"

            # Template namespace if not preserving
            if not self.preserve_ns and 'namespace' in resource.get('metadata', {}):
                resource['metadata']['namespace'] = '{{ .Release.Namespace }}'

            # Add release name prefix if not using original names
            # Skip for cluster-scoped resources like ClusterRole, ClusterRoleBinding, Namespace
            cluster_scoped_kinds = ['Namespace', 'ClusterRole', 'ClusterRoleBinding', 'ClusterRoleList',
                                     'PersistentVolume', 'StorageClass', 'CustomResourceDefinition']
            if not self.original_name and kind not in cluster_scoped_kinds:
                original_name = resource.get('metadata', {}).get('name', '')
                if original_name:
                    resource['metadata']['name'] = f'{{{{ include "{self.chart_name}.fullname" . }}}}-{original_name}'

            # Inject standard labels if requested
            if self.inject_labels:
                self._inject_standard_labels(resource)

            # Add common labels if specified
            if self.common_labels:
                self._add_common_labels(resource)

            # Detect and add Helm hooks if requested
            if self.detect_hooks:
                self._add_helm_hooks(resource)

            # Write template file
            template_path = self.templates_dir / filename

            # Check if this resource needs template escaping
            needs_escaping = self._needs_template_escaping(resource)

            if needs_escaping:
                # Write to string first, then escape
                import io
                stream = io.StringIO()
                self.yaml.dump(normalize_dict(resource), stream)
                content = stream.getvalue()

                # Escape {{ }} that are not Helm templates (i.e., not starting with .Values)
                # This is for Prometheus/Alertmanager templates
                escaped_content = self._escape_prometheus_templates(content)

                with open(template_path, 'w') as f:
                    f.write(escaped_content)
            else:
                with open(template_path, 'w') as f:
                    self.yaml.dump(normalize_dict(resource), f)

            report.templated += 1

    def _needs_template_escaping(self, resource: Dict[str, Any]) -> bool:
        """Check if resource needs template syntax escaping.

        Args:
            resource: Kubernetes resource

        Returns:
            True if resource needs escaping
        """
        # DISABLED: Template escaping doesn't work for resources with nested backticks
        # PrometheusRules contain templates like: {{ printf `...` $labels }}
        # which cannot be escaped with Helm's {{` ... `}} syntax
        #
        # Solution: Keep these resources as literal YAML without any escaping
        # Users can manually edit them if needed
        return False

    def _escape_prometheus_templates(self, content: str) -> str:
        """Escape Prometheus template syntax in YAML content.

        Wraps {{ }} patterns that don't start with .Values in {{`{{ }}`}}
        to prevent Helm from interpreting them.

        Args:
            content: YAML content as string

        Returns:
            Content with escaped Prometheus templates
        """
        import re

        # Simple approach: Find {{ }} that contain Prometheus-specific syntax
        # and wrap them in backticks

        # Prometheus/Alertmanager templates contain: $labels, $value, $externalLabels, printf, humanize, query, range
        # We need to match {{ }} that contain Prometheus-specific keywords
        # Challenge: these templates can contain nested braces like {instance="%s"}

        # Strategy: Match {{ followed by anything (including braces) until we find }}
        # but only if it contains Prometheus keywords
        # Use non-greedy match with DOTALL to handle multiline

        def escape_prom(match):
            template = match.group(0)
            # Don't double-escape
            if template.startswith('{{`'):
                return template

            # Check if this looks like a Prometheus template
            prom_indicators = ['$labels', '$value', '$external', 'printf', 'humanize', 'query', 'reReplaceAll']

            # If it starts with Helm indicators, don't escape
            content = template[2:-2].strip()  # Remove {{ and }}
            if content.startswith(('.', '-', 'include', 'define', 'toYaml', 'toJson', 'tpl')):
                return template

            # If it contains any Prometheus indicator, escape it
            if any(indicator in template for indicator in prom_indicators):
                return '{{`' + template + '`}}'

            # Default: if it contains $, escape it (likely Prometheus variable)
            if '$' in template:
                return '{{`' + template + '`}}'

            return template

        # Match {{ ... }} with minimal matching, allowing nested braces
        # This regex matches {{ followed by anything until the last }}
        # We process each match to decide if it needs escaping
        prometheus_pattern = r'\{\{(?:[^{}]|\{[^}]*\})*\}\}'

        escaped = re.sub(prometheus_pattern, escape_prom, content)
        return escaped

    def _write_helpers(self) -> None:
        """Write _helpers.tpl file."""
        # Use Jinja2 with variable_start_string to avoid conflict with Helm syntax
        env = Environment(
            loader=PackageLoader('yaml2helm', 'templates'),
            variable_start_string='<<<',
            variable_end_string='>>>',
        )
        template = env.get_template('_helpers.tpl')
        content = template.render(chart_name=self.chart_name)

        helpers_path = self.templates_dir / '_helpers.tpl'
        with open(helpers_path, 'w') as f:
            f.write(content)

    def _write_notes(self) -> None:
        """Write NOTES.txt file."""
        env = Environment(
            loader=PackageLoader('yaml2helm', 'templates'),
            variable_start_string='<<<',
            variable_end_string='>>>',
        )
        template = env.get_template('NOTES.txt')
        content = template.render(chart_name=self.chart_name)

        notes_path = self.templates_dir / 'NOTES.txt'
        with open(notes_path, 'w') as f:
            f.write(content)

    def _write_readme(self) -> None:
        """Write README.md file."""
        env = Environment(
            loader=PackageLoader('yaml2helm', 'templates'),
            variable_start_string='<<<',
            variable_end_string='>>>',
        )
        template = env.get_template('README.md')
        content = template.render(chart_name=self.chart_name)

        readme_path = self.chart_dir / 'README.md'
        with open(readme_path, 'w') as f:
            f.write(content)

    def _write_helmignore(self) -> None:
        """Write .helmignore file."""
        helmignore_content = """# Patterns to ignore when building packages.
# This supports shell glob matching, relative path matching, and
# negation (prefixed with !). Only one pattern per line.
.DS_Store
.git/
.gitignore
.bzr/
.bzrignore
.hg/
.hgignore
.svn/
*.swp
*.bak
*.tmp
*.orig
*~
.project
.idea/
*.tmproj
.vscode/
"""
        helmignore_path = self.chart_dir / '.helmignore'
        with open(helmignore_path, 'w') as f:
            f.write(helmignore_content)

    def _write_crd(self, resource: Dict[str, Any]) -> None:
        """Write CRD to crds/ directory.

        Args:
            resource: CustomResourceDefinition resource
        """
        if not self.crds_dir:
            return

        name = resource.get('metadata', {}).get('name', 'unnamed')
        filename = f"{name}.yaml"
        crd_path = self.crds_dir / filename

        with open(crd_path, 'w') as f:
            self.yaml.dump(normalize_dict(resource), f)

    def _inject_standard_labels(self, resource: Dict[str, Any]) -> None:
        """Inject standard Kubernetes labels using helpers.

        Args:
            resource: Kubernetes resource
        """
        if 'metadata' not in resource:
            resource['metadata'] = {}
        if 'labels' not in resource['metadata']:
            resource['metadata']['labels'] = {}

        # Add standard labels using Helm helpers
        labels = resource['metadata']['labels']
        if 'app.kubernetes.io/name' not in labels:
            labels['app.kubernetes.io/name'] = f'{{{{ include "{self.chart_name}.name" . }}}}'
        if 'app.kubernetes.io/instance' not in labels:
            labels['app.kubernetes.io/instance'] = '{{ .Release.Name }}'
        if 'app.kubernetes.io/version' not in labels:
            labels['app.kubernetes.io/version'] = '{{ .Chart.AppVersion }}'
        if 'app.kubernetes.io/managed-by' not in labels:
            labels['app.kubernetes.io/managed-by'] = '{{ .Release.Service }}'

    def _add_common_labels(self, resource: Dict[str, Any]) -> None:
        """Add custom common labels to resource.

        Args:
            resource: Kubernetes resource
        """
        if 'metadata' not in resource:
            resource['metadata'] = {}
        if 'labels' not in resource['metadata']:
            resource['metadata']['labels'] = {}

        labels = resource['metadata']['labels']
        for key, value in self.common_labels.items():
            if key not in labels:
                labels[key] = value

    def _add_helm_hooks(self, resource: Dict[str, Any]) -> None:
        """Detect and add Helm hook annotations.

        Args:
            resource: Kubernetes resource
        """
        kind = resource.get('kind')

        # Detect Jobs that look like hooks
        if kind == 'Job':
            name = resource.get('metadata', {}).get('name', '').lower()
            annotations = resource.get('metadata', {}).get('annotations', {})

            # Skip if already has hook annotation
            if 'helm.sh/hook' in annotations:
                return

            if 'metadata' not in resource:
                resource['metadata'] = {}
            if 'annotations' not in resource['metadata']:
                resource['metadata']['annotations'] = {}

            # Detect hook type from name
            if any(word in name for word in ['pre-install', 'preinstall']):
                resource['metadata']['annotations']['helm.sh/hook'] = 'pre-install'
            elif any(word in name for word in ['post-install', 'postinstall']):
                resource['metadata']['annotations']['helm.sh/hook'] = 'post-install'
            elif any(word in name for word in ['pre-upgrade', 'preupgrade']):
                resource['metadata']['annotations']['helm.sh/hook'] = 'pre-upgrade'
            elif any(word in name for word in ['post-upgrade', 'postupgrade']):
                resource['metadata']['annotations']['helm.sh/hook'] = 'post-upgrade'
            elif any(word in name for word in ['pre-delete', 'predelete']):
                resource['metadata']['annotations']['helm.sh/hook'] = 'pre-delete'
            elif any(word in name for word in ['post-delete', 'postdelete']):
                resource['metadata']['annotations']['helm.sh/hook'] = 'post-delete'
            elif any(word in name for word in ['test', 'check']):
                resource['metadata']['annotations']['helm.sh/hook'] = 'test'

    def _write_values_with_comments(self, file, values: Dict[str, Any], indent: int) -> None:
        """Write values.yaml with inline comments.

        Args:
            file: File handle
            values: Values dictionary
            indent: Current indentation level
        """
        indent_str = '  ' * indent

        for key, value in sorted(values.items()):
            if isinstance(value, dict):
                # Add comment for resource sections
                if indent == 0:
                    file.write(f"# Configuration for {key}\n")
                # If empty dict, write {} instead of null
                if not value:
                    file.write(f"{indent_str}{key}: {{}}\n")
                else:
                    file.write(f"{indent_str}{key}:\n")
                    self._write_values_with_comments(file, value, indent + 1)
            elif isinstance(value, list):
                file.write(f"{indent_str}{key}:\n")
                for item in value:
                    if isinstance(item, dict):
                        file.write(f"{indent_str}- ")
                        # Write dict items inline for lists
                        for k, v in item.items():
                            file.write(f"{k}: {self._format_value(v)}\n")
                            if k != list(item.keys())[-1]:
                                file.write(f"{indent_str}  ")
                    else:
                        file.write(f"{indent_str}- {self._format_value(item)}\n")
            else:
                # Add inline comment for known fields
                comment = self._get_field_comment(key)
                if comment:
                    file.write(f"{indent_str}{key}: {self._format_value(value)}  # {comment}\n")
                else:
                    file.write(f"{indent_str}{key}: {self._format_value(value)}\n")

        if indent == 0:
            file.write("\n")

    def _format_value(self, value: Any) -> str:
        """Format value for YAML output.

        Args:
            value: Value to format

        Returns:
            Formatted string
        """
        if isinstance(value, str):
            return f"'{value}'"
        return str(value)

    def _get_field_comment(self, field_name: str) -> str:
        """Get comment for common field names.

        Args:
            field_name: Field name

        Returns:
            Comment string or empty
        """
        comments = {
            'replicas': 'Number of replicas',
            'repository': 'Container image repository',
            'tag': 'Container image tag',
            'pullPolicy': 'Image pull policy',
            'port': 'Service port',
            'targetPort': 'Container target port',
            'type': 'Service type',
            'cpu': 'CPU resource',
            'memory': 'Memory resource',
        }
        return comments.get(field_name, '')

    def write_env_values(self, env_name: str, base_values: Dict[str, Any]) -> None:
        """Write environment-specific values file.

        Args:
            env_name: Environment name (dev, prod, etc.)
            base_values: Base values to use as template
        """
        env_values_path = self.chart_dir / f'values-{env_name}.yaml'

        with open(env_values_path, 'w') as f:
            f.write(f"# Values for {env_name} environment\n")
            f.write(f"# Override values from values.yaml for {env_name} deployment\n\n")
            # Write subset of values that commonly differ per environment
            env_values = self._extract_env_specific_values(base_values, env_name)
            self.yaml.dump(normalize_dict(env_values), f)

    def _extract_env_specific_values(self, values: Dict[str, Any], env_name: str) -> Dict[str, Any]:
        """Extract environment-specific values.

        Args:
            values: Full values dictionary
            env_name: Environment name

        Returns:
            Environment-specific values
        """
        env_values = {}

        # Typically replicas, resources, and ingress differ per environment
        for resource_name, resource_config in values.items():
            if isinstance(resource_config, dict):
                env_resource = {}
                if 'replicas' in resource_config:
                    # Suggest different replicas for environments
                    base_replicas = resource_config['replicas']
                    if env_name == 'prod':
                        env_resource['replicas'] = base_replicas * 2
                    elif env_name == 'dev':
                        env_resource['replicas'] = 1
                    else:
                        env_resource['replicas'] = base_replicas

                if 'resources' in resource_config:
                    # Include resources for customization
                    env_resource['resources'] = resource_config['resources']

                if env_resource:
                    env_values[resource_name] = env_resource

        return env_values
