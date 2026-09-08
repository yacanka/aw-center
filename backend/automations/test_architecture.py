"""Architecture tests for automation metadata and worker boundaries."""

import ast
from pathlib import Path

from django.test import SimpleTestCase
from django.utils.module_loading import import_string

from awcenter.job_executors import (
    local_job_kinds,
    resolve_job_executor,
    resolve_worker_executor,
    worker_job_kinds,
)
from jobs.contracts import JobExecutionFailure

from .catalog import DOORS_QUEUE, EXECUTOR_CATALOG, LOCAL_QUEUE, executor_kinds


class AutomationArchitectureTests(SimpleTestCase):
    """Lock down dependency direction and the static executor catalog."""

    def test_every_catalog_dotted_path_resolves_to_a_callable(self):
        for metadata in EXECUTOR_CATALOG:
            self.assertTrue(callable(import_string(metadata.dotted_path)), metadata.kind)

    def test_local_composition_root_cannot_resolve_doors_executor(self):
        self.assertTrue(executor_kinds(LOCAL_QUEUE))
        self.assertEqual(
            set(executor_kinds(DOORS_QUEUE)),
            {
                "doors.run_dxl",
                "doors.update_object",
                "doors.create_object",
                "doors.link_requirements",
            },
        )
        self.assertEqual(set(local_job_kinds()), set(executor_kinds(LOCAL_QUEUE)))
        with self.assertRaises(JobExecutionFailure):
            resolve_job_executor("doors.run_dxl")
        self.assertEqual(
            set(worker_job_kinds(include_doors=True)),
            set(executor_kinds(LOCAL_QUEUE)) | set(executor_kinds(DOORS_QUEUE)),
        )
        self.assertTrue(callable(resolve_worker_executor("doors.run_dxl")))

    def test_kernel_and_doors_tasks_keep_dependency_direction(self):
        root = Path(__file__).resolve().parents[1]
        kernel_files = tuple((root / "jobs").glob("*.py"))
        feature_roots = {"dcc", "excel", "integrations", "media_tools", "outlook", "word"}
        for path in kernel_files:
            imports = imported_roots(path)
            self.assertTrue(feature_roots.isdisjoint(imports), path.name)

        worker_imports = imported_roots(
            root / "integrations" / "doors" / "worker_tasks.py"
        )
        self.assertNotIn("jobs", worker_imports)
        self.assertNotIn("django.db", worker_imports)

        composition_source = (root / "awcenter" / "job_executors.py").read_text()
        self.assertNotIn("from dcc", composition_source)
        self.assertNotIn("from integrations", composition_source)
        self.assertNotIn("from word", composition_source)

    def test_jobs_internal_import_graph_is_acyclic(self):
        jobs_root = Path(__file__).resolve().parents[1] / "jobs"
        graph = internal_import_graph(jobs_root)

        self.assertIsNone(find_import_cycle(graph))
        self.assertNotIn("services", graph["workflow_services"])
        self.assertNotIn("services", graph["handoffs"])

    def test_feature_recipes_live_outside_the_jobs_kernel(self):
        root = Path(__file__).resolve().parents[1]

        self.assertTrue((root / "automations" / "recipes.py").is_file())
        self.assertFalse((root / "jobs" / "workflow_recipes.py").exists())
        jobs_urls = (root / "jobs" / "urls.py").read_text(encoding="utf-8")
        self.assertNotIn("retry", jobs_urls)
        self.assertNotIn("handoff", jobs_urls)

    def test_launcher_does_not_supervise_a_windows_server(self):
        root = Path(__file__).resolve().parents[2]
        launcher_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / "scripts" / "launcher").glob("*.py")
        ).casefold()
        self.assertNotIn("windows_bridge", launcher_source)
        self.assertNotIn("cheroot", launcher_source)


def imported_roots(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
            imports.add(node.module)
    return imports


def internal_import_graph(package_root):
    modules = {path.stem for path in package_root.glob("*.py") if path.name != "__init__.py"}
    graph = {module: set() for module in modules}
    for module in modules:
        path = package_root / f"{module}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level < 1:
                continue
            if node.module:
                target = node.module.split(".", 1)[0]
                if target in modules:
                    graph[module].add(target)
            else:
                graph[module].update(
                    alias.name for alias in node.names if alias.name in modules
                )
    return graph


def find_import_cycle(graph):
    visited = set()
    active = []

    def visit(node):
        if node in active:
            start = active.index(node)
            return active[start:] + [node]
        if node in visited:
            return None
        active.append(node)
        for target in graph[node]:
            cycle = visit(target)
            if cycle:
                return cycle
        active.pop()
        visited.add(node)
        return None

    for node in graph:
        cycle = visit(node)
        if cycle:
            return cycle
    return None
