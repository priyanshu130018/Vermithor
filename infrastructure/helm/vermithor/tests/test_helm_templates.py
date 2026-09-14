import os
import yaml


def test_chart_yaml_valid():
    chart_path = "infrastructure/helm/vermithor/Chart.yaml"
    assert os.path.exists(chart_path)
    with open(chart_path, "r", encoding="utf-8") as f:
        chart = yaml.safe_load(f)
    assert chart["name"] == "vermithor"
    assert chart["version"] == "0.1.0"
    assert chart["apiVersion"] == "v2"


def test_values_yaml_valid():
    values_path = "infrastructure/helm/vermithor/values.yaml"
    assert os.path.exists(values_path)
    with open(values_path, "r", encoding="utf-8") as f:
        values = yaml.safe_load(f)

    assert "global" in values
    assert "secrets" in values
    assert "existingSecret" in values["secrets"]
    assert "gateway" in values
    assert "frontend" in values
    assert "backend" in values
    assert "worker" in values
    assert "database" in values
    assert "redis" in values
    assert "observability" in values


def test_dev_and_prod_values_valid():
    dev_path = "infrastructure/helm/vermithor/values-dev.yaml"
    prod_path = "infrastructure/helm/vermithor/values-prod.yaml"
    assert os.path.exists(dev_path)
    assert os.path.exists(prod_path)

    with open(dev_path, "r", encoding="utf-8") as f:
        dev_values = yaml.safe_load(f)
    with open(prod_path, "r", encoding="utf-8") as f:
        prod_values = yaml.safe_load(f)

    assert dev_values["global"]["environment"] == "development"
    assert prod_values["global"]["environment"] == "production"
    assert dev_values["gateway"]["replicaCount"] == 1
    assert prod_values["gateway"]["replicaCount"] == 3
    assert prod_values["secrets"]["existingSecret"] == "vermithor-production-secrets"


def test_templates_exist():
    templates_dir = "infrastructure/helm/vermithor/templates"
    assert os.path.exists(templates_dir)

    expected_templates = [
        "_helpers.tpl",
        "backend-deployment.yaml",
        "worker-deployment.yaml",
    ]

    for tmpl in expected_templates:
        assert os.path.exists(os.path.join(templates_dir, tmpl)), f"Missing template {tmpl}"
