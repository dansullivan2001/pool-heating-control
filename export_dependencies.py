# export_dependencies.py

import ast
import os
import shutil
import subprocess
from pathlib import Path
from typing import Set

# ---------- CONFIG ----------
SOURCE_SCRIPT = "export_dependencies.py"       # Your main script
DEST_FOLDER = "exported_project"  # Where files and requirements go
GRAPH_FILE = "dependency_graph.svg"  # Visual graph output
# ----------------------------

EXTERNAL_LIBS: Set[str] = set()
INTERNAL_FILES: Set[Path] = set()
VISITED_FILES: Set[Path] = set()

def is_standard_lib(module_name: str) -> bool:
    import importlib.util, sysconfig
    from pathlib import Path

    if module_name in __import__('sys').builtin_module_names:
        return True

    spec = importlib.util.find_spec(module_name)
    if not spec or not spec.origin:
        return False

    stdlib_path = Path(sysconfig.get_path("stdlib")).resolve()
    origin_path = Path(spec.origin).resolve()

    # exclude site-packages (third-party packages)
    site_packages = Path(sysconfig.get_path("purelib")).resolve()
    if site_packages in origin_path.parents:
        return False

    return stdlib_path in origin_path.parents or origin_path == stdlib_path



def find_dependencies(file_path: Path, project_root: Path):
    file_path = file_path.resolve()
    if file_path in VISITED_FILES:
        return
    VISITED_FILES.add(file_path)

    INTERNAL_FILES.add(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=str(file_path))
        except SyntaxError:
            print(f"[Warning] Syntax error in {file_path}, skipping")
            return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                handle_import(alias.name, project_root)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            handle_import(node.module, project_root)

def handle_import(module_name: str, project_root: Path):
    """Resolve internal and external dependencies."""
    if module_name.startswith("."):
        return
    if is_standard_lib(module_name):
        return
    try:
        spec = __import__(module_name).__file__
        if spec and Path(spec).resolve().is_relative_to(project_root):
            find_dependencies(Path(spec), project_root)
        else:
            EXTERNAL_LIBS.add(module_name)
    except ModuleNotFoundError:
        print(f"[Warning] Module '{module_name}' not found, skipping.")

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
            f.write(lib + "\n")

def generate_dependency_graph(source_script: str, graph_file: str):
    """Use pydeps to generate a visual dependency graph."""
    subprocess.run([
        "pydeps",
        "--show-deps",
        "--max-bacon", "2",
        "-T", "svg",         # explicitly request SVG output
        "-o", graph_file,    # output file
        source_script
    ], check=True)

def main():
    project_root = Path.cwd()
    dest_folder = Path(DEST_FOLDER)
    dest_folder.mkdir(exist_ok=True)

    find_dependencies(Path(SOURCE_SCRIPT), project_root)
    copy_internal_files(dest_folder)
    write_requirements(dest_folder)

    # Generate visual graph
    generate_dependency_graph(SOURCE_SCRIPT, GRAPH_FILE)

    print(f"Export complete!")
    print(f"- Files copied to: {DEST_FOLDER}")
    print(f"- requirements.txt generated")
    print(f"- Dependency graph saved as: {GRAPH_FILE}")

if __name__ == "__main__":
    main()
