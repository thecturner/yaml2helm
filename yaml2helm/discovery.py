"""Discovery and parsing of Kubernetes YAML manifests."""

import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from .report import Report
from .util import is_k8s_resource, normalize_dict


class YAMLDiscovery:
    """Discover and parse YAML files."""

    def __init__(self, report: Report):
        self.report = report
        self.yaml = YAML(typ='safe', pure=True)

    def discover_files(self, input_path: str | Path | None) -> List[Path]:
        """Discover YAML files from input path or stdin.

        Args:
            input_path: File, directory, or None for stdin

        Returns:
            List of YAML file paths (empty if stdin)
        """
        if input_path is None:
            # stdin mode
            return []

        path = Path(input_path)

        if not path.exists():
            self.report.add_error(f"Input path does not exist: {path}")
            return []

        if path.is_file():
            self.report.files_discovered = 1
            return [path]

        if path.is_dir():
            yaml_files = sorted(path.rglob('*.yaml')) + sorted(path.rglob('*.yml'))
            self.report.files_discovered = len(yaml_files)
            return yaml_files

        return []

    def parse_file(self, file_path: Path) -> Iterator[Dict[str, Any]]:
        """Parse a YAML file and yield individual documents.

        Args:
            file_path: Path to YAML file

        Yields:
            Parsed YAML documents
        """
        try:
            with open(file_path, 'r') as f:
                for doc in self.yaml.load_all(f):
                    if doc is None:
                        continue
                    yield doc
        except YAMLError as e:
            self.report.bad_yaml += 1
            self.report.add_error(f"YAML parse error in {file_path}: {e}")
        except Exception as e:
            self.report.bad_yaml += 1
            self.report.add_error(f"Error reading {file_path}: {e}")

    def parse_stdin(self) -> Iterator[Dict[str, Any]]:
        """Parse YAML from stdin and yield individual documents.

        Yields:
            Parsed YAML documents
        """
        try:
            for doc in self.yaml.load_all(sys.stdin):
                if doc is None:
                    continue
                yield doc
        except YAMLError as e:
            self.report.bad_yaml += 1
            self.report.add_error(f"YAML parse error from stdin: {e}")
        except Exception as e:
            self.report.bad_yaml += 1
            self.report.add_error(f"Error reading stdin: {e}")

    def discover_and_parse(self, input_path: str | Path | None) -> List[Dict[str, Any]]:
        """Discover files and parse all Kubernetes resources.

        Args:
            input_path: File, directory, or None for stdin

        Returns:
            List of validated Kubernetes resources
        """
        resources = []

        if input_path is None:
            # Parse from stdin
            for doc in self.parse_stdin():
                if self._validate_resource(doc):
                    resources.append(normalize_dict(doc))
        else:
            # Parse from files
            files = self.discover_files(input_path)
            for file_path in files:
                for doc in self.parse_file(file_path):
                    if self._validate_resource(doc):
                        resources.append(normalize_dict(doc))

        return resources

    def _validate_resource(self, obj: Any) -> bool:
        """Validate that an object is a valid Kubernetes resource.

        Args:
            obj: Parsed YAML object

        Returns:
            True if valid, False otherwise
        """
        if not is_k8s_resource(obj):
            self.report.skipped += 1
            return False

        self.report.valid_objects += 1
        return True
