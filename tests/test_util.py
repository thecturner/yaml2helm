"""Tests for utility functions."""

import pytest
from yaml2helm.util import (
    normalize_dict,
    normalize_list,
    sanitize_name,
    get_nested_value,
    set_nested_value,
    is_k8s_resource,
    get_resource_identifier,
)


def test_normalize_dict():
    """Test dictionary normalization with sorted keys."""
    obj = {'z': 1, 'a': 2, 'b': {'y': 3, 'x': 4}}
    normalized = normalize_dict(obj)

    # Check that keys are sorted
    assert list(normalized.keys()) == ['a', 'b', 'z']
    assert list(normalized['b'].keys()) == ['x', 'y']


def test_normalize_list():
    """Test list normalization."""
    items = [{'b': 2, 'a': 1}, {'d': 4, 'c': 3}]
    normalized = normalize_list(items)

    # Check that nested dicts are normalized
    assert list(normalized[0].keys()) == ['a', 'b']
    assert list(normalized[1].keys()) == ['c', 'd']


def test_sanitize_name():
    """Test name sanitization."""
    assert sanitize_name('MyApp-Service') == 'myapp-service'
    assert sanitize_name('app_service_v1.2') == 'app-service-v1-2'
    assert sanitize_name('--test--') == 'test'


def test_get_nested_value():
    """Test getting nested values."""
    obj = {'spec': {'replicas': 3, 'template': {'spec': {'containers': []}}}}

    assert get_nested_value(obj, 'spec.replicas') == 3
    assert get_nested_value(obj, 'spec.template.spec.containers') == []
    assert get_nested_value(obj, 'spec.missing', 'default') == 'default'


def test_set_nested_value():
    """Test setting nested values."""
    obj = {}
    set_nested_value(obj, 'spec.replicas', 3)

    assert obj == {'spec': {'replicas': 3}}


def test_is_k8s_resource():
    """Test Kubernetes resource validation."""
    valid = {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {'name': 'my-service'}
    }
    assert is_k8s_resource(valid) is True

    # Missing apiVersion
    invalid1 = {'kind': 'Service', 'metadata': {'name': 'my-service'}}
    assert is_k8s_resource(invalid1) is False

    # Missing metadata.name
    invalid2 = {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {}}
    assert is_k8s_resource(invalid2) is False


def test_get_resource_identifier():
    """Test resource identifier generation."""
    resource = {
        'kind': 'Deployment',
        'metadata': {'name': 'my-app'}
    }
    assert get_resource_identifier(resource) == 'deployment-my-app'

    resource2 = {
        'kind': 'Service',
        'metadata': {'name': 'My_Service-v1.2'}
    }
    assert get_resource_identifier(resource2) == 'service-my-service-v1-2'
