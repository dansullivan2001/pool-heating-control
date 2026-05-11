import ast
import os
import shutil
import subprocess
import sysconfig
import importlib.metadata
import importlib.util
from pathlib import Path
from typing import Set

# ---------- CONFIG ----------
SOURCE_SCRIPT = "test_main_controller_gui.py"  # Your main script
DEST_FOLDER = "00_exported_project"           # Where files and requirements go
GRAPH_FILE = "dependency_graph.svg"           # Visual graph output
# ----------------------------

EXTERNAL_LIBS: Set[str] = set()
INTERNAL_FILES: Set[Path] = set()
VISITED_FILES: Set[Path] = set()


def is_stdlib(module_name: str) -> bool:
    """Return True if module is part of the standard library or built-in."""
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is None or spec.origin is None:
            return True
        stdlib_path = Path(sysconfig.get_path("stdlib"))
        return str(spec.origin).startswith(str(stdlib_path))
    except Exception:
        return False


def find_dependencies(file_path: Path, project_root: Path):
    """Parse a Python file and recursively find internal and external dependencies."""
    file_path = file_path.resolve()
    if file_path in VISITED_FILES:
        return
    VISITED_FILES.add(file_path)
    INTERNAL_FILES.add(file_path)

    if not file_path.exists() or not file_path.is_file():
        print(f"[Warning] File not found: {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=str(file_path))
        except SyntaxError:
            print(f"[Warning] Syntax error in {file_path}, skipping")
            return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                handle_import(alias.name, project_root, file_path)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            handle_import(node.module, project_root, file_path, level=node.level)


def handle_import(module_name: str, project_root: Path, current_file: Path, level: int = 0):
    """Resolve internal vs external dependencies and log classification."""
    micropython_builtins = {"machine", "utime", "umqtt", "onewire", "ds18x20"}
    
    top_module = module_name.split(".")[0]
    if top_module in micropython_builtins:
        print(f"[MicroPython] Skipping: {module_name}")
        return

    # Handle relative imports
    if level > 0 or module_name.startswith("."):
        rel_module = module_name.lstrip(".")
        target_dir = current_file.parent
        for _ in range(level - 1):
            target_dir = target_dir.parent
        if rel_module:
            target_dir = target_dir / rel_module.replace(".", "/")
        candidates = [target_dir.with_suffix(".py"), target_dir / "__init__.py"]
        found = False
        for candidate in candidates:
            if candidate.exists():
                find_dependencies(candidate, project_root)
                if candidate.name == "__init__.py":
                    for py_file in candidate.parent.rglob("*.py"):
                        find_dependencies(py_file, project_root)
                found = True
        if not found:
            print(f"[Relative] Could not resolve relative import: {module_name}")
        return

    # Absolute imports
    try:
        spec = importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        print(f"[Warning] Could not find module: {module_name}, skipping")
        return

    if spec is None or spec.origin is None:
        print(f"[Builtin/Stdlib] {module_name} (ignored)")
        return

    origin = Path(spec.origin)
    if not origin.exists() or not origin.is_file():
        print(f"[Non-file] {module_name} at {origin} (ignored)")
        return

    site_packages = Path(sysconfig.get_path("purelib")).resolve()

    if origin.is_relative_to(project_root):
        print(f"[Internal] {module_name} → {origin}")
        find_dependencies(origin, project_root)
        package_dir = origin.parent
        if (package_dir / "__init__.py").exists():
            for py_file in package_dir.rglob("*.py"):
                find_dependencies(py_file, project_root)
    elif origin.is_relative_to(site_packages):
        EXTERNAL_LIBS.add(top_module)
        print(f"[External] {module_name} → {origin}")
    else:
        EXTERNAL_LIBS.add(top_module)
        print(f"[External?] {module_name} → {origin} (unknown location)")


def copy_internal_files(dest_folder: Path):
    for file_path in INTERNAL_FILES:
        rel_path = file_path.relative_to(Path.cwd())
        dest_path = dest_folder / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(file_path, dest_path)


def write_requirements(dest_folder: Path):
    req_file = dest_folder / "requirements.txt"
    with open(req_file, "w", encoding="utf-8") as f:
        for lib in sorted(EXTERNAL_LIBS):
            version = None
            dist_name = None
            try:
                dist_name = lib
                version = importlib.metadata.version(lib)
            except importlib.metadata.PackageNotFoundError:
                top = lib.split(".")[0]
                if top != lib:
                    try:
                        dist_name = top
                        version = importlib.metadata.version(top)
                    except importlib.metadata.PackageNotFoundError:
                        pass
            if version:
                f.write(f"{dist_name}=={version}\n")
            else:
                f.write(f"{lib}\n")
                print(f"[Warning] Could not resolve external dependency: {lib}")


def generate_dependency_graph(source_script: Path, output_file: Path):
    """Generate a visual dependency graph using pydeps on a single entrypoint."""
    output_path = output_file.resolve()
    print(f"[Info] Generating dependency graph for {source_script} → {output_path}")

    subprocess.run([
        "python3", "-m", "pydeps",
        str(source_script),
        "--max-bacon", "2",
        "--show-deps",
        "-o", str(output_path),      # use -o instead of --output=
        "--cluster",
        "--pylib",
        "--externals",
        "--verbose",
    ], check=True, cwd=Path.cwd())






def main():
    project_root = Path.cwd()
    dest_folder = Path(DEST_FOLDER)
    dest_folder.mkdir(exist_ok=True)

    # 1. Find all dependencies
    find_dependencies(Path(SOURCE_SCRIPT), project_root)

    # 2. Copy internal files
    copy_internal_files(dest_folder)

    # 3. Write requirements.txt
    write_requirements(dest_folder)

    # 4. Generate dependency graph on the main entrypoint
    generate_dependency_graph((SOURCE_SCRIPT), Path(DEST_FOLDER) / GRAPH_FILE)

    print(f"Export complete!")
    print(f"- Files copied to: {DEST_FOLDER}")
    print(f"- requirements.txt generated")
    print(f"- Dependency graph saved as: {GRAPH_FILE}")


if __name__ == "__main__":
    main()
