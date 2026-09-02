"""Architecture and security fitness functions for the first-production target."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from django.test import SimpleTestCase


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
FEATURE_PACKAGES = frozenset(
    {
        "attention",
        "automations",
        "compliance",
        "dcc",
        "ddf",
        "excel",
        "integrations",
        "media_tools",
        "orgs",
        "outlook",
        "pdf",
        "pptxgallery",
        "projects",
        "word",
    }
)
LEGACY_PROJECT_PACKAGES = frozenset(
    {"aesa", "blok30", "blok4050", "gokbey", "havasoj", "hys", "ozgur", "piku"}
)
LEGACY_RUNTIME_PACKAGES = frozenset({"common", "core", "doors", "docproof", "teamcenter"})


class ArchitectureFitnessTests(SimpleTestCase):
    def test_production_import_graph_is_acyclic(self):
        modules = production_modules()
        graph = import_graph(modules)
        cycles = [component for component in strongly_connected_components(graph) if len(component) > 1]

        self.assertEqual(cycles, [], f"Production import cycles: {cycles}")

    def test_jobs_kernel_does_not_import_feature_executors(self):
        violations = []
        for module, path in production_modules().items():
            if module != "jobs" and not module.startswith("jobs."):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                imported = imported_root(node)
                if imported in FEATURE_PACKAGES:
                    violations.append(f"{module}:{getattr(node, 'lineno', 0)} -> {imported}")
        self.assertEqual(violations, [])

    def test_composition_root_does_not_own_vendor_adapters(self):
        forbidden = {
            "assessment_client.py",
            "docproof.py",
            "doors.py",
            "jira.py",
            "mail.py",
            "teamcenter.py",
        }
        present = {
            path.name
            for path in (BACKEND_ROOT / "awcenter").glob("*.py")
            if path.name in forbidden
        }
        self.assertEqual(present, set())

    def test_vendor_clients_live_behind_the_integrations_boundary(self):
        required = {
            "assessment.py",
            "docproof.py",
            "doors/client.py",
            "jira/client.py",
            "mail.py",
            "teamcenter/client.py",
        }
        missing = {
            relative
            for relative in required
            if not (BACKEND_ROOT / "integrations" / relative).is_file()
        }
        legacy = {
            relative
            for relative in {
                "awcenter/assessment_client.py",
                "docproof/client.py",
                "doors/client/client.py",
                "teamcenter/client.py",
                "teamcenter/transport.py",
            }
            if (BACKEND_ROOT / relative).exists()
        }
        self.assertEqual(missing, set())
        self.assertEqual(legacy, set())

    def test_automations_do_not_import_dcc_implementation_modules(self):
        violations = []
        for module, path in production_modules().items():
            if module != "automations" and not module.startswith("automations."):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if imported_root(node) == "dcc":
                    violations.append(f"{module}:{getattr(node, 'lineno', 0)}")
        self.assertEqual(violations, [])

    def test_legacy_runtime_packages_and_model_identity_are_absent(self):
        for package in LEGACY_RUNTIME_PACKAGES:
            self.assertFalse(
                any((BACKEND_ROOT / package).glob("*.py")),
                f"Legacy runtime package remains: {package}",
            )
        for slug in LEGACY_PROJECT_PACKAGES:
            self.assertFalse((BACKEND_ROOT / "projects" / slug).exists())
        violations = source_matches(r"_meta\.app_label", production_modules())
        self.assertEqual(violations, [])

    def test_browser_auth_and_frontend_boundaries_are_fail_closed(self):
        backend_source = combined_source(production_modules())
        self.assertNotIn("TokenAuthentication", backend_source)
        self.assertNotIn("rest_framework.authtoken", backend_source)

        frontend_files = list((REPOSITORY_ROOT / "frontend/src").rglob("*.ts")) + list(
            (REPOSITORY_ROOT / "frontend/src").rglob("*.vue")
        )
        direct_axios = []
        store_locator = []
        credential_storage = []
        for path in frontend_files:
            source = path.read_text(encoding="utf-8")
            relative = path.relative_to(REPOSITORY_ROOT).as_posix()
            if ("/components/" in relative or "/views/" in relative) and re.search(
                r"from\s+['\"]axios['\"]", source
            ):
                direct_axios.append(relative)
            if re.search(r"window\.\$[A-Za-z0-9_]*Store\b", source):
                store_locator.append(relative)
            for line_number, line in enumerate(source.splitlines(), start=1):
                if "localStorage" in line and re.search(
                    r"token|jsessionid|credential", line, re.IGNORECASE
                ):
                    credential_storage.append(f"{relative}:{line_number}")
        self.assertEqual(direct_axios, [])
        self.assertEqual(store_locator, [])
        self.assertEqual(credential_storage, [])

    def test_root_urls_publish_only_canonical_api_and_no_public_media(self):
        source = (BACKEND_ROOT / "awcenter/urls.py").read_text(encoding="utf-8")
        self.assertNotIn('path("media/', source)
        self.assertNotIn('path("download/', source)
        for route in re.findall(r'path\("([^"<]*)', source):
            if route in {
                "",
                "admin/",
                "app/",
                "health/live/",
                "health/ready/",
                "internal/doors-runner/v1/",
            }:
                continue
            self.assertTrue(route.startswith("api/"), route)


def production_modules() -> dict[str, Path]:
    modules = {}
    for path in BACKEND_ROOT.rglob("*.py"):
        relative = path.relative_to(BACKEND_ROOT)
        if "__pycache__" in relative.parts or "migrations" in relative.parts:
            continue
        if "tests" in relative.parts or path.name.startswith("test"):
            continue
        if path.name == "manage.py":
            module = "manage"
        else:
            parts = list(relative.with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            module = ".".join(parts)
        if module:
            modules[module] = path
    return modules


def import_graph(modules: dict[str, Path]) -> dict[str, set[str]]:
    graph = {module: set() for module in modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = longest_module_prefix(alias.name, modules)
                    if target and target != module:
                        graph[module].add(target)
            elif isinstance(node, ast.ImportFrom):
                base = resolve_from_module(module, path.name == "__init__.py", node)
                candidates = [
                    *([] if node.module is None else [base]),
                    *(f"{base}.{alias.name}" for alias in node.names if base),
                ]
                for candidate in candidates:
                    target = longest_module_prefix(candidate, modules)
                    if target and target != module:
                        graph[module].add(target)
    return graph


def resolve_from_module(module: str, is_package: bool, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    package = module.split(".") if is_package else module.split(".")[:-1]
    keep = max(0, len(package) - node.level + 1)
    prefix = package[:keep]
    if node.module:
        prefix.extend(node.module.split("."))
    return ".".join(prefix)


def longest_module_prefix(candidate: str, modules: dict[str, Path]) -> str | None:
    parts = candidate.split(".") if candidate else []
    for length in range(len(parts), 0, -1):
        value = ".".join(parts[:length])
        if value in modules:
            return value
    return None


def imported_root(node) -> str | None:
    if isinstance(node, ast.Import) and node.names:
        return node.names[0].name.split(".", 1)[0]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return node.module.split(".", 1)[0]
    return None


def strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack = []
    indices = {}
    lowlinks = {}
    on_stack = set()
    components = []

    def visit(node):
        nonlocal index
        indices[node] = lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph[node]:
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component = []
        while True:
            target = stack.pop()
            on_stack.remove(target)
            component.append(target)
            if target == node:
                break
        components.append(sorted(component))

    for node in graph:
        if node not in indices:
            visit(node)
    return components


def source_matches(pattern: str, modules: dict[str, Path]) -> list[str]:
    compiled = re.compile(pattern)
    return [module for module, path in modules.items() if compiled.search(path.read_text(encoding="utf-8"))]


def combined_source(modules: dict[str, Path]) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in modules.values())
