"""Value extraction and templating for Kubernetes resources."""

import copy
from typing import Any, Dict, List, Set
from .util import get_nested_value, set_nested_value


def make_values_path(path: str) -> str:
    """Create a Helm values path, using index function for keys with hyphens.

    Args:
        path: Dot-separated path like "resource-name.image.tag"

    Returns:
        Helm template path like 'index .Values "resource-name" "image" "tag"' or '.Values.resource.image.tag'
    """
    parts = path.split('.')

    # Check if any part has hyphens
    has_hyphens = any('-' in part for part in parts)

    if has_hyphens:
        # Use index function for all parts if any has hyphens
        quoted_parts = [f'"{part}"' for part in parts]
        return f'index .Values {" ".join(quoted_parts)}'
    else:
        # Use simple dot notation
        return f'.Values.{".".join(parts)}'


class ValueExtractor:
    """Extract values from Kubernetes resources and replace with Helm templates."""

    # Fields to extract and template with their value paths and defaults
    EXTRACTION_RULES = {
        'Deployment': [
            ('spec.replicas', 'replicas', 1),
            ('spec.template.spec.containers[0].image', 'image.repository', None),
            ('spec.template.spec.containers[0].image_tag', 'image.tag', 'latest'),
            ('spec.template.spec.containers[0].resources', 'resources', {}),
            ('spec.template.spec.nodeSelector', 'nodeSelector', {}),
            ('spec.template.spec.tolerations', 'tolerations', []),
            ('spec.template.spec.affinity', 'affinity', {}),
        ],
        'StatefulSet': [
            ('spec.replicas', 'replicas', 1),
            ('spec.template.spec.containers[0].image', 'image.repository', None),
            ('spec.template.spec.containers[0].image_tag', 'image.tag', 'latest'),
            ('spec.template.spec.containers[0].resources', 'resources', {}),
            ('spec.template.spec.nodeSelector', 'nodeSelector', {}),
            ('spec.template.spec.tolerations', 'tolerations', []),
            ('spec.template.spec.affinity', 'affinity', {}),
        ],
        'Service': [
            ('spec.type', 'service.type', 'ClusterIP'),
            ('spec.ports', 'service.ports', []),
        ],
        'Ingress': [
            ('spec.rules', 'ingress.rules', []),
            ('spec.tls', 'ingress.tls', []),
        ],
        'HorizontalPodAutoscaler': [
            ('spec.minReplicas', 'autoscaling.minReplicas', 1),
            ('spec.maxReplicas', 'autoscaling.maxReplicas', 10),
            ('spec.targetCPUUtilizationPercentage', 'autoscaling.targetCPUUtilizationPercentage', 80),
        ],
    }

    def __init__(self, include_cluster_specific: bool = False, resource_scoped: bool = True):
        self.include_cluster_specific = include_cluster_specific
        self.resource_scoped = resource_scoped
        self.values: Dict[str, Any] = {}
        self.conflicts: List[str] = []

    def extract_and_template(self, resources: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Extract values from resources and create templated versions.

        Args:
            resources: List of Kubernetes resources

        Returns:
            Tuple of (templated resources, extracted values dict)
        """
        if self.resource_scoped:
            return self._extract_resource_scoped(resources)
        else:
            return self._extract_field_scoped(resources)

    def _extract_field_scoped(self, resources: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Extract values using field-scoped approach (old behavior, causes conflicts)."""
        templated_resources = []

        for resource in resources:
            templated = self._process_resource(copy.deepcopy(resource))
            templated_resources.append(templated)

        return templated_resources, self.values

    def _extract_resource_scoped(self, resources: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Extract values using resource-scoped approach (avoids conflicts)."""
        from .util import sanitize_name

        templated_resources = []
        values = {}

        for resource in resources:
            resource_copy = copy.deepcopy(resource)
            kind = resource_copy.get('kind', '')
            name = resource_copy.get('metadata', {}).get('name', 'unnamed')

            # Create resource-scoped key
            resource_key = sanitize_name(name)

            # Initialize resource scope
            if resource_key not in values:
                values[resource_key] = {}

            # Process resource with scoped values
            templated = self._process_resource_scoped(resource_copy, resource_key, values[resource_key])
            templated_resources.append(templated)

        return templated_resources, values

    def _process_resource_scoped(self, resource: Dict[str, Any], resource_key: str, resource_values: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single resource with resource-scoped values.

        Args:
            resource: Kubernetes resource
            resource_key: Sanitized resource name for values scope
            resource_values: Dictionary to store this resource's values

        Returns:
            Templated resource
        """
        kind = resource.get('kind', '')

        # Extract containers and images
        self._extract_containers_scoped(resource, resource_key, resource_values)

        # Extract kind-specific fields
        if kind == 'Deployment' or kind == 'StatefulSet':
            if 'spec' in resource and 'replicas' in resource['spec']:
                resource_values['replicas'] = resource['spec']['replicas']
                values_path = make_values_path(f"{resource_key}.replicas")
                resource['spec']['replicas'] = f"{{{{ {values_path} }}}}"

            # Extract resources
            containers_path = self._get_containers_path(resource)
            if containers_path:
                containers = get_nested_value(resource, containers_path, [])
                if containers and isinstance(containers[0], dict) and 'resources' in containers[0]:
                    resource_values['resources'] = containers[0]['resources']
                    values_path = make_values_path(f"{resource_key}.resources")
                    # Wrap in parens if using index function
                    if values_path.startswith('index'):
                        containers[0]['resources'] = f"{{{{- toYaml ({values_path}) | nindent 10 }}}}"
                    else:
                        containers[0]['resources'] = f"{{{{- toYaml {values_path} | nindent 10 }}}}"

            # Extract nodeSelector
            node_selector_path = 'spec.template.spec.nodeSelector' if kind in ['Deployment', 'StatefulSet'] else 'spec.nodeSelector'
            node_selector = get_nested_value(resource, node_selector_path)
            if node_selector:
                resource_values['nodeSelector'] = node_selector
                values_path = make_values_path(f"{resource_key}.nodeSelector")
                # Wrap in parens if using index function
                if values_path.startswith('index'):
                    set_nested_value(resource, node_selector_path, f"{{{{- toYaml ({values_path}) | nindent 8 }}}}")
                else:
                    set_nested_value(resource, node_selector_path, f"{{{{- toYaml {values_path} | nindent 8 }}}}")

        elif kind == 'Service':
            if 'spec' in resource:
                if 'type' in resource['spec']:
                    resource_values['type'] = resource['spec']['type']
                    values_path = make_values_path(f"{resource_key}.type")
                    resource['spec']['type'] = f"{{{{ {values_path} }}}}"

                if 'ports' in resource['spec']:
                    resource_values['ports'] = resource['spec']['ports']
                    values_path = make_values_path(f"{resource_key}.ports")
                    # Wrap in parens if using index function
                    if values_path.startswith('index'):
                        resource['spec']['ports'] = f"{{{{- toYaml ({values_path}) | nindent 2 }}}}"
                    else:
                        resource['spec']['ports'] = f"{{{{- toYaml {values_path} | nindent 2 }}}}"

        # Extract environment variables
        self._extract_env_vars_scoped(resource, resource_key, resource_values)

        return resource

    def _process_resource(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single resource and extract values.

        Args:
            resource: Kubernetes resource

        Returns:
            Templated resource
        """
        kind = resource.get('kind', '')

        # Extract common metadata
        self._extract_metadata(resource)

        # Extract kind-specific fields
        if kind in self.EXTRACTION_RULES:
            for field_path, value_path, default in self.EXTRACTION_RULES[kind]:
                self._extract_field(resource, field_path, value_path, default)

        # Extract container-level fields
        self._extract_containers(resource)

        # Extract environment variables
        self._extract_env_vars(resource)

        return resource

    def _extract_metadata(self, resource: Dict[str, Any]) -> None:
        """Extract metadata fields."""
        metadata = resource.get('metadata', {})

        # Extract labels (keep them literal unless flag is set)
        if self.include_cluster_specific and 'labels' in metadata:
            self._merge_value('labels', metadata['labels'])

        # Extract annotations (keep them literal unless flag is set)
        if self.include_cluster_specific and 'annotations' in metadata:
            self._merge_value('annotations', metadata['annotations'])

    def _extract_containers(self, resource: Dict[str, Any]) -> None:
        """Extract container-specific fields from pod specs."""
        containers_path = self._get_containers_path(resource)
        if not containers_path:
            return

        containers = get_nested_value(resource, containers_path, [])

        for i, container in enumerate(containers):
            if not isinstance(container, dict):
                continue

            # Extract and split image into repository and tag
            if 'image' in container:
                image_full = container['image']
                repo, tag = self._split_image(image_full)

                # Set default values if not already set
                if 'image' not in self.values:
                    self.values['image'] = {}

                if 'repository' not in self.values['image']:
                    self.values['image']['repository'] = repo

                if 'tag' not in self.values['image']:
                    self.values['image']['tag'] = tag

                # Template the image field
                container['image'] = '{{ .Values.image.repository }}:{{ .Values.image.tag }}'

    def _extract_env_vars(self, resource: Dict[str, Any]) -> None:
        """Extract environment variables from containers."""
        containers_path = self._get_containers_path(resource)
        if not containers_path:
            return

        containers = get_nested_value(resource, containers_path, [])

        for i, container in enumerate(containers):
            if not isinstance(container, dict):
                continue

            env_vars = container.get('env', [])
            if not env_vars:
                continue

            # Extract env vars with values (not valueFrom)
            for env in env_vars:
                if isinstance(env, dict) and 'name' in env and 'value' in env:
                    env_key = f"env.{env['name']}"
                    env_value = env['value']

                    # Store in values
                    if 'env' not in self.values:
                        self.values['env'] = {}

                    self.values['env'][env['name']] = env_value

                    # Template the value
                    values_path = make_values_path(f"env.{env['name']}")
                    env['value'] = f"{{{{ {values_path} }}}}"

    def _extract_field(self, resource: Dict[str, Any], field_path: str, value_path: str, default: Any) -> None:
        """Extract a specific field and replace with template.

        Args:
            resource: Resource to extract from
            field_path: Path in resource (e.g., 'spec.replicas')
            value_path: Path in values.yaml (e.g., 'replicas')
            default: Default value if field not found
        """
        value = get_nested_value(resource, field_path)

        if value is None:
            return

        # Store in values dict
        self._merge_value(value_path, value if value is not None else default)

        # Replace with template
        values_path = make_values_path(value_path)
        template = f"{{{{ {values_path} }}}}"

        # For complex types, use toYaml
        if isinstance(value, (dict, list)):
            # Wrap in parens if using index function
            if values_path.startswith('index'):
                template = f"{{{{- toYaml ({values_path}) | nindent 8 }}}}"
            else:
                template = f"{{{{- toYaml {values_path} | nindent 8 }}}}"

        set_nested_value(resource, field_path, template)

    def _merge_value(self, path: str, value: Any) -> None:
        """Merge a value into the values dict, detecting conflicts.

        Args:
            path: Dot-separated path (e.g., 'image.tag')
            value: Value to merge
        """
        parts = path.split('.')
        current = self.values

        # Navigate to parent
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        # Set or check conflict
        key = parts[-1]
        if key in current and current[key] != value:
            self.conflicts.append(f"Conflict at {path}: {current[key]} vs {value}")
        else:
            current[key] = value

    def _get_containers_path(self, resource: Dict[str, Any]) -> str | None:
        """Get the path to containers in a resource.

        Args:
            resource: Kubernetes resource

        Returns:
            Path to containers or None
        """
        kind = resource.get('kind', '')

        if kind in ['Deployment', 'StatefulSet', 'DaemonSet', 'ReplicaSet', 'Job']:
            return 'spec.template.spec.containers'
        elif kind == 'Pod':
            return 'spec.containers'
        elif kind == 'CronJob':
            return 'spec.jobTemplate.spec.template.spec.containers'

        return None

    def _split_image(self, image: str) -> tuple[str, str]:
        """Split image into repository and tag.

        Args:
            image: Full image string (e.g., 'nginx:1.19', 'myregistry/app:v1.0')

        Returns:
            Tuple of (repository, tag)
        """
        if ':' in image:
            parts = image.rsplit(':', 1)
            return parts[0], parts[1]
        else:
            return image, 'latest'

    def get_conflicts(self) -> List[str]:
        """Get list of conflicts detected during extraction."""
        return self.conflicts

    def _extract_containers_scoped(self, resource: Dict[str, Any], resource_key: str, resource_values: Dict[str, Any]) -> None:
        """Extract container-specific fields with resource scoping."""
        containers_path = self._get_containers_path(resource)
        if not containers_path:
            return

        containers = get_nested_value(resource, containers_path, [])

        for i, container in enumerate(containers):
            if not isinstance(container, dict):
                continue

            # Extract and split image into repository and tag
            if 'image' in container:
                image_full = container['image']
                repo, tag = self._split_image(image_full)

                # Store in resource scope
                if 'image' not in resource_values:
                    resource_values['image'] = {}

                resource_values['image']['repository'] = repo
                resource_values['image']['tag'] = tag

                # Template the image field
                repo_path = make_values_path(f"{resource_key}.image.repository")
                tag_path = make_values_path(f"{resource_key}.image.tag")
                container['image'] = f"{{{{ {repo_path} }}}}:{{{{ {tag_path} }}}}"

    def _extract_env_vars_scoped(self, resource: Dict[str, Any], resource_key: str, resource_values: Dict[str, Any]) -> None:
        """Extract environment variables with resource scoping."""
        containers_path = self._get_containers_path(resource)
        if not containers_path:
            return

        containers = get_nested_value(resource, containers_path, [])

        for i, container in enumerate(containers):
            if not isinstance(container, dict):
                continue

            env_vars = container.get('env', [])
            if not env_vars:
                continue

            # Extract env vars with values (not valueFrom)
            for env in env_vars:
                if isinstance(env, dict) and 'name' in env and 'value' in env:
                    env_name = env['name']
                    env_value = env['value']

                    # Store in resource scope
                    if 'env' not in resource_values:
                        resource_values['env'] = {}

                    resource_values['env'][env_name] = env_value

                    # Template the value
                    values_path = make_values_path(f"{resource_key}.env.{env_name}")
                    env['value'] = f"{{{{ {values_path} }}}}"
