"""Integration tests for yaml2helm."""

import pytest
import subprocess
from pathlib import Path
from ruamel.yaml import YAML


def test_end_to_end_conversion(tmp_path):
    """Test complete conversion pipeline."""
    # Create input YAML
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    deployment_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
  labels:
    app: nginx
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:1.19
        ports:
        - containerPort: 80
        resources:
          limits:
            cpu: 100m
            memory: 128Mi
          requests:
            cpu: 100m
            memory: 128Mi
"""
    (input_dir / "deployment.yaml").write_text(deployment_yaml)

    service_yaml = """
apiVersion: v1
kind: Service
metadata:
  name: nginx-service
spec:
  type: LoadBalancer
  selector:
    app: nginx
  ports:
  - protocol: TCP
    port: 80
    targetPort: 80
"""
    (input_dir / "service.yaml").write_text(service_yaml)

    # Run conversion (import and run directly)
    from yaml2helm.discovery import YAMLDiscovery
    from yaml2helm.extractors import ValueExtractor
    from yaml2helm.chartwriter import ChartWriter
    from yaml2helm.report import Report

    report = Report()
    discovery = YAMLDiscovery(report)
    resources = discovery.discover_and_parse(input_dir)

    assert report.valid_objects == 2

    extractor = ValueExtractor()
    templated_resources, values = extractor.extract_and_template(resources)

    output_dir = tmp_path / "output"
    writer = ChartWriter("test-chart", output_dir, enable_schema=True)
    writer.write_chart(templated_resources, values, report)

    # Verify chart structure
    chart_dir = output_dir / "test-chart"
    assert (chart_dir / "Chart.yaml").exists()
    assert (chart_dir / "values.yaml").exists()
    assert (chart_dir / "values.schema.json").exists()
    assert (chart_dir / "templates").is_dir()
    assert (chart_dir / "templates" / "_helpers.tpl").exists()
    assert (chart_dir / "templates" / "NOTES.txt").exists()
    assert (chart_dir / "README.md").exists()
    assert (chart_dir / ".helmignore").exists()

    # Verify values.yaml content (resource-scoped)
    yaml = YAML()
    with open(chart_dir / "values.yaml") as f:
        values_content = yaml.load(f)

    assert 'nginx-deployment' in values_content
    assert 'image' in values_content['nginx-deployment']
    assert values_content['nginx-deployment']['image']['repository'] == 'nginx'
    assert values_content['nginx-deployment']['image']['tag'] == '1.19'
    assert values_content['nginx-deployment']['replicas'] == 3

    # Verify template files exist
    template_files = list((chart_dir / "templates").glob("*.yaml"))
    assert len(template_files) >= 2  # At least deployment and service


def test_idempotent_conversion(tmp_path):
    """Test that running conversion twice produces identical output."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    yaml_content = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-config
data:
  key: value
"""
    (input_dir / "config.yaml").write_text(yaml_content)

    from yaml2helm.discovery import YAMLDiscovery
    from yaml2helm.extractors import ValueExtractor
    from yaml2helm.chartwriter import ChartWriter
    from yaml2helm.report import Report

    # First run
    report1 = Report()
    discovery1 = YAMLDiscovery(report1)
    resources1 = discovery1.discover_and_parse(input_dir)
    extractor1 = ValueExtractor()
    templated1, values1 = extractor1.extract_and_template(resources1)

    output_dir1 = tmp_path / "output1"
    writer1 = ChartWriter("test", output_dir1)
    writer1.write_chart(templated1, values1, report1)

    # Second run
    report2 = Report()
    discovery2 = YAMLDiscovery(report2)
    resources2 = discovery2.discover_and_parse(input_dir)
    extractor2 = ValueExtractor()
    templated2, values2 = extractor2.extract_and_template(resources2)

    output_dir2 = tmp_path / "output2"
    writer2 = ChartWriter("test", output_dir2)
    writer2.write_chart(templated2, values2, report2)

    # Compare outputs
    yaml = YAML()

    values_file1 = output_dir1 / "test" / "values.yaml"
    values_file2 = output_dir2 / "test" / "values.yaml"

    with open(values_file1) as f1, open(values_file2) as f2:
        values_content1 = yaml.load(f1)
        values_content2 = yaml.load(f2)

    assert values_content1 == values_content2
