"""CLI entry point for yaml2helm."""

import sys
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

import typer
from rich.console import Console
from rich.table import Table

from .discovery import YAMLDiscovery
from .extractors import ValueExtractor
from .chartwriter import ChartWriter
from .report import Report

app = typer.Typer(
    name="yaml2helm",
    help="Convert Kubernetes YAML manifests into Helm charts",
    add_completion=False
)
console = Console()


@app.command()
def convert(
    name: str = typer.Option(..., "--name", "-n", help="Chart name"),
    input_path: Optional[str] = typer.Option(None, "--in", "-i", help="Input file or directory (stdin if omitted)"),
    output_dir: str = typer.Option("./charts", "--out", "-o", help="Output directory for charts"),
    kustomize_dir: Optional[str] = typer.Option(None, "--kustomize", "-k", help="Run kustomize build on directory and convert output"),
    resource_scoped: bool = typer.Option(True, "--resource-scoped/--field-scoped", help="Scope values to resources (recommended) or share across resources"),
    crd_dir: bool = typer.Option(False, "--crd-dir", help="Place CRDs in separate crds/ directory"),
    preserve_ns: bool = typer.Option(False, "--preserve-ns", help="Preserve original namespaces instead of templating"),
    original_name: bool = typer.Option(True, "--original-name/--prefix-release-name", help="Preserve original resource names (default) or add release name prefix"),
    inject_labels: bool = typer.Option(False, "--inject-labels", help="Inject standard Kubernetes labels to all resources"),
    common_labels: Optional[List[str]] = typer.Option(None, "--common-labels", help="Add custom labels to all resources (key=value format)"),
    include_cluster_specific: bool = typer.Option(False, "--include-cluster", help="Include cluster-specific fields in templates"),
    enable_schema: bool = typer.Option(True, "--schema/--no-schema", help="Generate values.schema.json"),
    run_lint: bool = typer.Option(True, "--lint/--no-lint", help="Run helm lint after generation"),
    run_template: bool = typer.Option(True, "--template/--no-template", help="Run helm template after generation"),
    strict: bool = typer.Option(False, "--strict", help="Fail on helm lint/template errors"),
    generate_makefile: bool = typer.Option(False, "--makefile", help="Generate Makefile with helm target"),
    description: Optional[str] = typer.Option(None, "--description", help="Chart description"),
    app_version: Optional[str] = typer.Option(None, "--app-version", help="Application version"),
    keywords: Optional[List[str]] = typer.Option(None, "--keywords", help="Chart keywords"),
    detect_hooks: bool = typer.Option(False, "--detect-hooks", help="Automatically detect and add Helm hook annotations"),
    set_values: Optional[List[str]] = typer.Option(None, "--set", help="Override values (key=value format)"),
    values_comments: bool = typer.Option(True, "--values-comments/--no-values-comments", help="Add comments to values.yaml"),
    multi_env: Optional[List[str]] = typer.Option(None, "--env", help="Generate environment-specific values files"),
) -> None:
    """Convert Kubernetes YAML manifests to Helm chart."""

    # Initialize report
    report = Report()

    # Parse common labels
    labels_dict = {}
    if common_labels:
        labels_dict = _parse_key_value_pairs(common_labels, "common-labels")

    # Parse set values
    set_values_dict = {}
    if set_values:
        set_values_dict = _parse_key_value_pairs(set_values, "set")

    # Handle kustomize build if specified
    if kustomize_dir and input_path:
        console.print("[bold red]Error:[/bold red] Cannot use both --kustomize and --in flags together")
        sys.exit(1)

    if kustomize_dir:
        console.print(f"[bold blue]Running kustomize build on {kustomize_dir}...[/bold blue]")
        kustomize_output = _run_kustomize_build(kustomize_dir, report)
        if not kustomize_output:
            console.print("[bold red]kustomize build failed![/bold red]")
            sys.exit(1)

        # Parse kustomize output from string
        discovery = YAMLDiscovery(report)
        resources = _parse_kustomize_output(kustomize_output, discovery)
        console.print(f"[green]✓[/green] Built and parsed kustomize output, found {report.valid_objects} valid resources")
    else:
        # Step 1: Discover and parse YAML files
        console.print(f"[bold blue]Discovering YAML manifests...[/bold blue]")
        discovery = YAMLDiscovery(report)
        resources = discovery.discover_and_parse(Path(input_path) if input_path else None)

    if not resources:
        console.print("[bold red]No valid Kubernetes resources found![/bold red]")
        if report.errors:
            console.print("\n[bold red]Errors:[/bold red]")
            for error in report.errors:
                console.print(f"  • {error}")
        sys.exit(1)

    console.print(f"[green]✓[/green] Discovered {report.files_discovered} files, found {report.valid_objects} valid resources")

    # Step 2: Extract values and template
    console.print(f"\n[bold blue]Extracting values and templating resources...[/bold blue]")
    extractor = ValueExtractor(
        include_cluster_specific=include_cluster_specific,
        resource_scoped=resource_scoped
    )
    templated_resources, values = extractor.extract_and_template(resources)

    # Track conflicts
    conflicts = extractor.get_conflicts()
    for conflict in conflicts:
        report.add_conflict(conflict)

    if report.conflicts_count > 0:
        console.print(f"[yellow]⚠[/yellow]  Found {report.conflicts_count} conflicts during extraction")

    console.print(f"[green]✓[/green] Templated {len(templated_resources)} resources")

    # Apply set values overrides
    if set_values_dict:
        values = _merge_set_values(values, set_values_dict)
        console.print(f"[green]✓[/green] Applied {len(set_values_dict)} value overrides")

    # Step 3: Write chart
    console.print(f"\n[bold blue]Writing Helm chart...[/bold blue]")
    output_path = Path(output_dir)
    writer = ChartWriter(
        name, output_path,
        enable_schema=enable_schema,
        crd_dir=crd_dir,
        preserve_ns=preserve_ns,
        original_name=original_name,
        inject_labels=inject_labels,
        common_labels=labels_dict,
        detect_hooks=detect_hooks,
        values_comments=values_comments,
        description=description,
        app_version=app_version,
        keywords=keywords
    )
    writer.write_chart(templated_resources, values, report)

    # Generate multi-environment values if requested
    if multi_env:
        for env in multi_env:
            writer.write_env_values(env, values)
            console.print(f"[green]✓[/green] Generated values-{env}.yaml")

    console.print(f"[green]✓[/green] Chart written to {report.chart_path}")

    # Step 4: Generate Makefile if requested
    if generate_makefile:
        _generate_makefile(report.chart_path, name, kustomize_dir)

    # Step 5: Run helm checks
    helm_available = _check_helm_available()

    if helm_available and run_lint:
        console.print(f"\n[bold blue]Running helm lint...[/bold blue]")
        lint_success = _run_helm_lint(report.chart_path, report, strict)
        if not lint_success and strict:
            console.print("[bold red]✗ helm lint failed (strict mode)[/bold red]")
            _print_summary(report)
            sys.exit(1)

    if helm_available and run_template:
        console.print(f"\n[bold blue]Running helm template...[/bold blue]")
        template_success = _run_helm_template(report.chart_path, report, strict)
        if not template_success and strict:
            console.print("[bold red]✗ helm template failed (strict mode)[/bold red]")
            _print_summary(report)
            sys.exit(1)

    # Step 6: Print summary
    _print_summary(report)

    if report.errors_count > 0 or (report.conflicts_count > 0):
        sys.exit(1)


def _check_helm_available() -> bool:
    """Check if helm is available on PATH."""
    try:
        result = subprocess.run(
            ["helm", "version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_helm_lint(chart_path: Path, report: Report, strict: bool) -> bool:
    """Run helm lint on the chart."""
    try:
        result = subprocess.run(
            ["helm", "lint", str(chart_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            console.print("[green]✓[/green] helm lint passed")
            return True
        else:
            console.print(f"[yellow]⚠[/yellow]  helm lint had issues:\n{result.stdout}")
            report.add_error(f"helm lint failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        console.print("[yellow]⚠[/yellow]  helm lint timed out")
        report.add_error("helm lint timed out")
        return False
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow]  helm lint error: {e}")
        report.add_error(f"helm lint error: {e}")
        return False


def _run_helm_template(chart_path: Path, report: Report, strict: bool) -> bool:
    """Run helm template on the chart."""
    try:
        result = subprocess.run(
            ["helm", "template", "test-release", str(chart_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            console.print("[green]✓[/green] helm template passed")
            return True
        else:
            console.print(f"[yellow]⚠[/yellow]  helm template had issues:\n{result.stderr}")
            report.add_error(f"helm template failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        console.print("[yellow]⚠[/yellow]  helm template timed out")
        report.add_error("helm template timed out")
        return False
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow]  helm template error: {e}")
        report.add_error(f"helm template error: {e}")
        return False


def _print_summary(report: Report) -> None:
    """Print conversion summary."""
    console.print("\n[bold]Summary:[/bold]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")

    summary = report.summary()
    table.add_row("Files discovered", str(summary['files_discovered']))
    table.add_row("Valid objects", str(summary['valid_objects']))
    table.add_row("Skipped", str(summary['skipped']))
    table.add_row("Bad YAML", str(summary['bad_yaml']))
    table.add_row("Templated", str(summary['templated']))
    table.add_row("Conflicts", str(summary['conflicts_count']))
    table.add_row("Errors", str(summary['errors_count']))

    console.print(table)

    if summary['chart_path']:
        console.print(f"\n[bold green]Chart written to:[/bold green] {summary['chart_path']}")

    if report.conflicts:
        console.print("\n[bold yellow]Conflicts:[/bold yellow]")
        for conflict in report.conflicts:
            console.print(f"  • {conflict}")

    if report.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for error in report.errors:
            console.print(f"  • {error}")


def _run_kustomize_build(kustomize_dir: str, report: Report) -> Optional[str]:
    """Run kustomize build and return output.

    Args:
        kustomize_dir: Directory containing kustomization.yaml
        report: Report object to track errors

    Returns:
        Kustomize build output or None on failure
    """
    # Try kustomize command first
    kustomize_cmd = None
    if _check_command_available("kustomize"):
        kustomize_cmd = ["kustomize", "build", kustomize_dir]
    elif _check_command_available("kubectl"):
        kustomize_cmd = ["kubectl", "kustomize", kustomize_dir]
    else:
        report.add_error("Neither 'kustomize' nor 'kubectl' command found. Please install one of them.")
        return None

    try:
        result = subprocess.run(
            kustomize_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            return result.stdout
        else:
            report.add_error(f"kustomize build failed: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        report.add_error("kustomize build timed out")
        return None
    except Exception as e:
        report.add_error(f"kustomize build error: {e}")
        return None


def _check_command_available(command: str) -> bool:
    """Check if a command is available on PATH."""
    try:
        result = subprocess.run(
            ["which", command],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def _parse_kustomize_output(output: str, discovery: 'YAMLDiscovery') -> List[Dict]:
    """Parse kustomize build output (multi-document YAML).

    Args:
        output: Kustomize build output string
        discovery: YAMLDiscovery instance

    Returns:
        List of parsed resources
    """
    from io import StringIO

    resources = []
    stream = StringIO(output)

    for doc in discovery.yaml.load_all(stream):
        if doc is None:
            continue
        if discovery._validate_resource(doc):
            from .util import normalize_dict
            resources.append(normalize_dict(doc))

    return resources


def _generate_makefile(chart_path: Path, chart_name: str, kustomize_dir: Optional[str] = None) -> None:
    """Generate Makefile with helm chart generation target.

    Args:
        chart_path: Path to the chart directory
        chart_name: Name of the chart
        kustomize_dir: Optional kustomize directory path
    """
    makefile_content = f"""# Helm Chart Generation
# Generated by yaml2helm

.PHONY: helm
helm: ## Generate Helm chart from manifests
"""

    if kustomize_dir:
        makefile_content += f"""\t@echo "Building kustomize and generating Helm chart..."
\t@kustomize build {kustomize_dir} 2>/dev/null | yaml2helm --name {chart_name} --out {chart_path.parent} || \\
\t kubectl kustomize {kustomize_dir} | yaml2helm --name {chart_name} --out {chart_path.parent}
"""
    else:
        makefile_content += f"""\t@echo "Generating Helm chart..."
\t@yaml2helm --name {chart_name} --in ./manifests --out {chart_path.parent}
"""

    makefile_content += """
.PHONY: helm-lint
helm-lint: helm ## Lint generated Helm chart
\t@helm lint """ + str(chart_path) + """

.PHONY: helm-template
helm-template: helm ## Template Helm chart (dry-run)
\t@helm template test-release """ + str(chart_path) + """

.PHONY: helm-install
helm-install: helm ## Install Helm chart
\t@helm install """ + chart_name + " " + str(chart_path) + """

.PHONY: help
help: ## Show this help message
\t@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\\033[36m%-20s\\033[0m %s\\n", $$1, $$2}'
"""

    makefile_path = Path.cwd() / "Makefile.helm"
    with open(makefile_path, 'w') as f:
        f.write(makefile_content)

    console.print(f"\n[bold green]✓[/bold green] Generated {makefile_path}")
    console.print("[dim]Run 'make -f Makefile.helm help' to see available targets[/dim]")


def _parse_key_value_pairs(pairs: List[str], flag_name: str) -> Dict[str, str]:
    """Parse key=value pairs from command line flags.

    Args:
        pairs: List of key=value strings
        flag_name: Name of flag for error messages

    Returns:
        Dictionary of parsed key-value pairs
    """
    result = {}
    for pair in pairs:
        if '=' not in pair:
            console.print(f"[bold red]Error:[/bold red] Invalid --{flag_name} format: '{pair}'. Expected key=value")
            sys.exit(1)
        key, value = pair.split('=', 1)
        result[key.strip()] = value.strip()
    return result


def _merge_set_values(values: Dict[str, Any], set_values: Dict[str, str]) -> Dict[str, Any]:
    """Merge --set values into extracted values using dot notation.

    Args:
        values: Extracted values dictionary
        set_values: Values to override from --set flags

    Returns:
        Merged values dictionary
    """
    from copy import deepcopy
    result = deepcopy(values)

    for key, value in set_values.items():
        # Support dot notation: nginx.replicas=5
        parts = key.split('.')
        current = result

        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        # Try to convert value to appropriate type
        final_value: Any = value
        if value.isdigit():
            final_value = int(value)
        elif value.lower() in ('true', 'false'):
            final_value = value.lower() == 'true'
        elif value.replace('.', '', 1).isdigit():
            final_value = float(value)

        current[parts[-1]] = final_value

    return result


if __name__ == "__main__":
    app()
