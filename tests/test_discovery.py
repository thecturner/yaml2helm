"""Tests for YAML discovery."""

import pytest
from pathlib import Path
from yaml2helm.discovery import YAMLDiscovery
from yaml2helm.report import Report


def test_discover_files(tmp_path):
    """Test file discovery."""
    # Create test files
    (tmp_path / "test1.yaml").write_text("apiVersion: v1\nkind: Pod")
    (tmp_path / "test2.yml").write_text("apiVersion: v1\nkind: Service")
    (tmp_path / "test.txt").write_text("not yaml")

    report = Report()
    discovery = YAMLDiscovery(report)
    files = discovery.discover_files(tmp_path)

    assert len(files) == 2
    assert report.files_discovered == 2


def test_parse_valid_yaml(tmp_path):
    """Test parsing valid YAML."""
    yaml_content = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  containers:
  - name: nginx
    image: nginx:latest
"""
    yaml_file = tmp_path / "valid.yaml"
    yaml_file.write_text(yaml_content)

    report = Report()
    discovery = YAMLDiscovery(report)
    docs = list(discovery.parse_file(yaml_file))

    assert len(docs) == 1
    assert docs[0]['kind'] == 'Pod'
    assert docs[0]['metadata']['name'] == 'test-pod'


def test_parse_multi_doc_yaml(tmp_path):
    """Test parsing multi-document YAML."""
    yaml_content = """
apiVersion: v1
kind: Service
metadata:
  name: svc1
---
apiVersion: v1
kind: Service
metadata:
  name: svc2
"""
    yaml_file = tmp_path / "multi.yaml"
    yaml_file.write_text(yaml_content)

    report = Report()
    discovery = YAMLDiscovery(report)
    docs = list(discovery.parse_file(yaml_file))

    assert len(docs) == 2
    assert docs[0]['metadata']['name'] == 'svc1'
    assert docs[1]['metadata']['name'] == 'svc2'


def test_parse_invalid_yaml(tmp_path):
    """Test parsing invalid YAML."""
    yaml_content = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  invalid: [unclosed
"""
    yaml_file = tmp_path / "invalid.yaml"
    yaml_file.write_text(yaml_content)

    report = Report()
    discovery = YAMLDiscovery(report)
    docs = list(discovery.parse_file(yaml_file))

    assert len(docs) == 0
    assert report.bad_yaml == 1


def test_discover_and_parse(tmp_path):
    """Test complete discovery and parsing."""
    yaml_content = """
apiVersion: v1
kind: Service
metadata:
  name: my-service
spec:
  type: ClusterIP
"""
    (tmp_path / "service.yaml").write_text(yaml_content)

    # Invalid resource (missing metadata.name)
    invalid_content = """
apiVersion: v1
kind: Pod
metadata: {}
"""
    (tmp_path / "invalid.yaml").write_text(invalid_content)

    report = Report()
    discovery = YAMLDiscovery(report)
    resources = discovery.discover_and_parse(tmp_path)

    assert len(resources) == 1
    assert report.valid_objects == 1
    assert report.skipped == 1
