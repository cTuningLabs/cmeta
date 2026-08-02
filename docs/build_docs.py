#!/usr/bin/env python3
"""
Documentation builder for cMeta API

This script generates comprehensive Sphinx documentation for all classes and functions 
in the cMeta library. It automatically discovers all modules, classes, and functions
and creates proper RST files with cross-references.

Usage:
    python build_docs.py [--build] [--clean]
    
Arguments:
    --build: Also build HTML documentation after generating RST files
    --clean: Clean the build directory before generating documentation
"""

import argparse
import os
import sys
import inspect
import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple, Any, Dict


# Written guides (Markdown) that live in docs/ and are copied into the Sphinx
# source tree so they become part of the published site. Order = TOC order.
GUIDE_FILES = [
    "README.md",
    "motivation.md",
    "installation.md",
    "common-commands.md",
    "using-cmeta.md",
    "error-handling.md",
    "async-and-concurrency.md",
    "configuration.md",
    "cplatform.md",
    "history.md",
    "known-issues.md",
]

# Sub-directory (inside the Sphinx source dir) that receives the copies.
GUIDES_SUBDIR = "guides"

# Links in the guides that point outside the copied set (e.g. ../README.md,
# ../CITATION.cff, ../.claude/skills/...) are rewritten to the public repo so
# they still work on the published site.
GITHUB_BLOB_BASE = "https://github.com/cTuningLabs/cmeta/blob/main/"


class CMataDocBuilder:
    """Documentation builder for cMeta API."""

    def __init__(self, docs_dir: Path = None,
                       cmeta_dir: Path = None,
                       site_dir: Path = None):
        """Initialize the documentation builder.
        
        Args:
            docs_dir: Path to the docs directory. If None, uses the directory containing this script.
        """
        if docs_dir is None:
            self.docs_dir = Path(__file__).parent
            self.lang = None
        else:
            self.docs_dir = Path(docs_dir)
            self.lang = self.docs_dir.name 
            
        self.cmeta_path = cmeta_dir
        self.api_dir = self.docs_dir / "api"
        self.build_dir = site_dir
        
        # Add parent directory to Python path so we can import cmeta package
        sys.path.insert(0, str(self.docs_dir.parent))
        
    def clean_build_dir(self):
        """Clean the build directory."""
        if self.build_dir.exists():
            print(f"Cleaning build directory: {self.build_dir}")
            shutil.rmtree(self.build_dir)
            
    def get_cmeta_modules(self) -> List[Tuple[str, Any, Path]]:
        """Get all Python modules from the cMeta directory.
        
        Returns:
            List of tuples containing (module_name, module_object, file_path)
        """
        modules = []
        
        for file_path in self.cmeta_path.rglob("*.py"):
            if 'internal-repo' in str(file_path):
                continue
            if file_path.name == "__init__.py":
                continue
            if file_path.name == "__main__.py":
                continue
                
            # Convert file path to module name
            relative_path = file_path.relative_to(self.cmeta_path)
            module_name = str(relative_path.with_suffix("")).replace(os.sep, ".")
            
            # Prepend 'cmeta.' to make it a proper package module
            full_module_name = f"cmeta.{module_name}"

            try:
                # Try to import the module using importlib
                import importlib
                module = importlib.import_module(full_module_name)
                modules.append((full_module_name, module, file_path))
            except Exception as e:
                print(f"Warning: Could not import {full_module_name}: {e}")
        
        return modules
    
    def get_module_members(self, module: Any) -> Dict[str, List[str]]:
        """Get categorized members of a module.
        
        Args:
            module: The module object to inspect
            
        Returns:
            Dictionary with categories as keys and lists of member names as values
        """
        members = {
            'classes': [],
            'functions': [],
            'exceptions': [],
            'constants': []
        }
        
        for name, obj in inspect.getmembers(module):
            if name.startswith('_'):
                continue
                
            if inspect.isclass(obj) and obj.__module__ == module.__name__:
                if issubclass(obj, Exception):
                    members['exceptions'].append(name)
                else:
                    members['classes'].append(name)
            elif inspect.isfunction(obj) and obj.__module__ == module.__name__:
                members['functions'].append(name)
            elif not inspect.ismodule(obj) and not inspect.isclass(obj) and not inspect.isfunction(obj):
                if isinstance(obj, (str, int, float, bool, list, dict, tuple)):
                    members['constants'].append(name)
                    
        return members
    
    def generate_module_rst(self, module_name: str, module: Any, file_path: Path) -> str:
        """Generate RST file for a module.
        
        Args:
            module_name: Full module name (e.g., 'cmeta.core')
            module: Module object
            file_path: Path to the module file
            
        Returns:
            Generated RST filename
        """
        rst_content = []
        
        # Module header
        simple_name = module_name.split('.')[-1]
#        module_title = f"{simple_name} module"
        module_title = f"{module_name} module"
        rst_content.append(module_title)
        rst_content.append("=" * len(module_title))
        rst_content.append("")
        
        # Module docstring
        if hasattr(module, "__doc__") and module.__doc__:
            rst_content.append(module.__doc__.strip())
            rst_content.append("")
        
        # Get module members
        members = self.get_module_members(module)
        
        # Add sections for different member types
        if members['classes']:
            rst_content.append("Classes")
            rst_content.append("-" * 7)
            rst_content.append("")
            for class_name in sorted(members['classes']):
                rst_content.append(f".. autoclass:: {module_name}.{class_name}")
                rst_content.append("   :members:")
                rst_content.append("   :undoc-members:")
                rst_content.append("   :show-inheritance:")
                rst_content.append("")
        
        if members['functions']:
            rst_content.append("Functions")
            rst_content.append("-" * 9)
            rst_content.append("")
            for func_name in sorted(members['functions']):
                rst_content.append(f".. autofunction:: {module_name}.{func_name}")
                rst_content.append("")
        
        if members['exceptions']:
            rst_content.append("Exceptions")
            rst_content.append("-" * 10)
            rst_content.append("")
            for exc_name in sorted(members['exceptions']):
                rst_content.append(f".. autoexception:: {module_name}.{exc_name}")
                rst_content.append("")
        
        if members['constants']:
            rst_content.append("Constants")
            rst_content.append("-" * 9)
            rst_content.append("")
            for const_name in sorted(members['constants']):
                rst_content.append(f".. autodata:: {module_name}.{const_name}")
                rst_content.append("")
        
        # Fallback: if no specific members found, use automodule
        if not any(members.values()):
            rst_content.append("Module Contents")
            rst_content.append("-" * 15)
            rst_content.append("")
            rst_content.append(f".. automodule:: {module_name}")
            rst_content.append("   :members:")
            rst_content.append("   :undoc-members:")
            rst_content.append("   :show-inheritance:")
            rst_content.append("")
        
        # Write RST file
        rst_filename = module_name.replace(".", "_") + ".rst"
        rst_path = self.api_dir / rst_filename
        
        with open(rst_path, "w", encoding="utf-8") as f:
            f.write("\n".join(rst_content))
        
        return rst_filename
    
    def generate_api_index_rst(self, module_files: List[str]):
        """Generate API index.rst file.
        
        Args:
            module_files: List of generated RST filenames
        """
        # Get version information
        try:
            version_file = self.cmeta_path / "version.py"
            version_ns = {}
            with open(version_file) as f:
                exec(f.read(), version_ns)
            version = version_ns.get('__version__', 'Unknown')
        except:
            version = 'Unknown'

        rst_content = [
            f"API Reference (v{version})",
            "=" * (len(f"API Reference (v{version})")),
            "",
            f"This section contains the complete API reference for cMeta v{version}.",
            "",
            ".. toctree::",
            "   :maxdepth: 2",
            ""
        ]
        
        # Add all module files to toctree
        for rst_file in sorted(module_files):
            rst_content.append(f"   {rst_file[:-4]}")  # Remove .rst extension
        
        with open(self.api_dir / "index.rst", "w", encoding="utf-8") as f:
            f.write("\n".join(rst_content))
    
    def generate_main_index_rst(self, guide_entries=None):
        """Generate main index.rst file.

        Args:
            guide_entries: Toctree entries for the copied Markdown guides.
        """
        # Check if index.rst already exists and has manual edits (e.g., PDF download links)
        index_file = self.docs_dir / "index.rst"
        
        if index_file.exists():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
                # If the file contains "Download Documentation", preserve it
                if "Download Documentation" in existing_content:
                    print("Preserving existing index.rst with manual edits")
                    return
            except Exception as e:
                print(f"Warning: Could not read existing index.rst: {e}")
        
        # Get version information
        try:
            version_file = self.cmeta_path / "version.py"
            version_ns = {}
            with open(version_file) as f:
                exec(f.read(), version_ns)
            version = version_ns.get('__version__', 'Unknown')
        except:
            version = 'Unknown'
            
        rst_content = [
            "cMeta Documentation",
            "===================",
            "",
            f"Welcome to cMeta v{version} documentation!",
            "",
            ".. toctree::",
            "   :maxdepth: 2",
            f"   :caption: cMeta v{version} Contents:",
            "",
            "   home",
        ]

        # Written guides (Markdown, copied in by copy_guides())
        if guide_entries:
            rst_content += [
                "",
                ".. toctree::",
                "   :maxdepth: 2",
                "   :caption: Guides:",
                "",
            ]
            rst_content += [f"   {entry}" for entry in guide_entries]

        rst_content += [
            "",
            ".. toctree::",
            "   :maxdepth: 2",
            "   :caption: API Reference:",
            "",
            "   api/index",
            "",
            "Indices and tables",
            "==================",
            "",
            "* :ref:`genindex`",
            "* :ref:`modindex`",
            "* :ref:`search`"
        ]

        with open(self.docs_dir / "index.rst", "w", encoding="utf-8") as f:
            f.write("\n".join(rst_content))

    def _rewrite_guide_link(self, target: str, copied: set) -> str:
        """Rewrite one Markdown link target for use inside the Sphinx source tree.

        Links to another copied guide are left alone (MyST resolves them).
        Anything else that is repo-relative is turned into a GitHub blob URL.

        Args:
            target: The raw link target from the Markdown source.
            copied: Set of guide file names that were copied.

        Returns:
            str: The rewritten link target.
        """
        if target.startswith(("http://", "https://", "mailto:", "#")):
            return target

        path, sep, anchor = target.partition("#")
        if not path:
            return target

        # A sibling guide that we copied - keep the relative link.
        if path in copied:
            return target

        # Anything else is relative to docs/ - point at the repository.
        repo_rel = os.path.normpath(os.path.join("docs", path)).replace(os.sep, "/")
        return GITHUB_BLOB_BASE + repo_rel + (sep + anchor if anchor else "")

    def copy_guides(self) -> List[str]:
        """Copy the Markdown guides into the Sphinx source tree.

        The guides live in docs/*.md while Sphinx reads from docs/en/. Sphinx
        cannot read sources above its root, so they are copied into
        docs/en/guides/ on every build and their repo-relative links are
        rewritten.

        Returns:
            List[str]: Toctree entries (e.g. "guides/installation") in TOC order.
        """
        import re

        source_dir = self.docs_dir.parent          # .../docs
        target_dir = self.docs_dir / GUIDES_SUBDIR  # .../docs/en/guides

        # Always start clean so removed guides don't linger.
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        available = {name for name in GUIDE_FILES if (source_dir / name).is_file()}
        entries = []

        link_re = re.compile(r"(\]\()([^)\s]+)(\))")

        for name in GUIDE_FILES:
            src = source_dir / name
            if not src.is_file():
                print(f"Warning: guide not found, skipping: {src}")
                continue

            text = src.read_text(encoding="utf-8")
            text = link_re.sub(
                lambda m: m.group(1) + self._rewrite_guide_link(m.group(2), available) + m.group(3),
                text,
            )

            (target_dir / name).write_text(text, encoding="utf-8")
            entries.append(f"{GUIDES_SUBDIR}/{Path(name).stem}")

        print(f"Copied {len(entries)} guides into {target_dir}")

        return entries

    def generate_documentation(self):
        """Generate all documentation files."""
        print("Generating cMeta API documentation...")
        
        # Create directories if they don't exist
        self.api_dir.mkdir(parents=True, exist_ok=True)
        
        # Get all cmeta modules
        modules = self.get_cmeta_modules()
        module_files = []
        
        print(f"Found {len(modules)} modules to document")
        
        # Generate RST files for each module
        for module_name, module, file_path in modules:
            print(f"Processing {module_name}...")
            try:
                rst_file = self.generate_module_rst(module_name, module, file_path)
                module_files.append(rst_file)
            except Exception as e:
                print(f"Error processing {module_name}: {e}")
        
        # Generate API index file
        self.generate_api_index_rst(module_files)

        # Copy the written Markdown guides into the Sphinx source tree
        guide_entries = self.copy_guides()

        # Generate main index file
        self.generate_main_index_rst(guide_entries)
        
        print(f"Generated documentation for {len(module_files)} modules")
        print("Documentation files created in:", self.docs_dir)
        
        return len(module_files) > 0
    
    def build_html(self):
        """Build HTML documentation using Sphinx."""
        print("Building HTML documentation...")
        
        # Get version for versioned directory
        try:
            version_file = self.cmeta_path / "version.py"
            version_ns = {}
            with open(version_file) as f:
                exec(f.read(), version_ns)
            version = version_ns.get('__version__', 'unknown')
        except:
            version = 'unknown'
        
        html_build_dir = self.build_dir / "html" 
        if self.lang is not None:
            html_build_dir /= self.lang
        
        try:
            # Run sphinx-build
            cmd = [
                sys.executable, "-m", "sphinx",
                "-b", "html",
                "-E",  # Force rebuild of all files (don't use cached environment)
                "-d", str(self.build_dir / "doctrees"),
                str(self.docs_dir),
                str(html_build_dir)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.docs_dir))
            
            if result.returncode == 0:
                print(f"HTML documentation built successfully in: {html_build_dir}")
                
                # Create versioned copy of HTML documentation
                versioned_html_dir = self.build_dir / "html" 
                if self.lang is not None:
                    versioned_html_dir /= self.lang
                versioned_html_dir /= f"v{version}"
                try:
                    print(f"Creating versioned HTML copy in: {versioned_html_dir}")
                    
                    # Remove existing versioned directory if it exists
                    if versioned_html_dir.exists():
                        shutil.rmtree(versioned_html_dir)
                    
                    # Create versioned directory
                    versioned_html_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Copy all files from main HTML build to versioned directory
                    # We need to copy contents, not the directory itself
                    for item in html_build_dir.iterdir():
                        if item.name.startswith('v') and item.is_dir():
                            # Skip existing versioned directories
                            continue
                        
                        dest_path = versioned_html_dir / item.name
                        if item.is_dir():
                            shutil.copytree(item, dest_path)
                        else:
                            shutil.copy2(item, dest_path)
                    
                    print(f"Versioned HTML documentation created: {versioned_html_dir}")
                    print(f"Latest documentation available at: {html_build_dir / 'index.html'}")
                    print(f"Versioned documentation available at: {versioned_html_dir / 'index.html'}")
                    
                    # Copy any existing PDFs to the HTML directories
                    self._copy_existing_pdfs_to_html(version)
                    
                except Exception as copy_error:
                    print(f"Warning: Could not create versioned HTML copy: {copy_error}")
                    # This is not a fatal error, the main HTML docs were still built successfully
                
                return True
            else:
                print("Error building HTML documentation:")
                print(result.stdout)
                print(result.stderr)
                return False
                
        except Exception as e:
            print(f"Error running Sphinx build: {e}")
            return False

    def build_pdf(self):
        """Build PDF documentation using Sphinx."""
        print("Building PDF documentation...")
        
        # Get version for filename
        try:
            version_file = self.cmeta_path / "version.py"
            version_ns = {}
            with open(version_file) as f:
                exec(f.read(), version_ns)
            version = version_ns.get('__version__', 'unknown')
        except:
            version = 'unknown'
        
        latex_build_dir = self.build_dir / "latex"
        
        try:
            # First, build LaTeX
            print("Building LaTeX files...")
            cmd = [
                sys.executable, "-m", "sphinx",
                "-b", "latex",
                "-d", str(self.build_dir / "doctrees"),
                str(self.docs_dir),
                str(latex_build_dir)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.docs_dir))
            
            if result.returncode != 0:
                print("Error building LaTeX documentation:")
                print(result.stdout)
                print(result.stderr)
                return False
            
            print("LaTeX files built successfully")
            
            # Try to build PDF with pdflatex (if available)
            tex_file = latex_build_dir / f"cmeta-{version}.tex"
            if tex_file.exists():
                print("Attempting to build PDF with pdflatex...")
                try:
                    # Run pdflatex twice for proper cross-references
                    for i in range(2):
                        pdf_cmd = ["pdflatex", "-interaction=nonstopmode", f"cmeta-{version}.tex"]
                        pdf_result = subprocess.run(pdf_cmd, capture_output=True, text=True, cwd=str(latex_build_dir))
                        
                        if pdf_result.returncode != 0:
                            print(f"Warning: pdflatex run {i+1} had issues (this is often normal for the first run)")
                    
                    # Check if PDF was created
                    versioned_pdf_file = latex_build_dir / f"cmeta-{version}.pdf"
                    if versioned_pdf_file.exists():
                        print(f"PDF documentation built successfully: {versioned_pdf_file}")
                        
                        # Create a generic cmeta.pdf copy
                        generic_pdf_file = latex_build_dir / "cmeta.pdf"
                        try:
                            shutil.copy2(versioned_pdf_file, generic_pdf_file)
                            print(f"Generic PDF created: {generic_pdf_file}")
                        except Exception as e:
                            print(f"Warning: Could not create generic PDF copy: {e}")
                        
                        # Copy PDFs to HTML directories if they exist
                        self._copy_pdfs_to_html_dirs(versioned_pdf_file, generic_pdf_file, version)
                        
                        return True
                    else:
                        print("PDF file was not created, but LaTeX files are available")
                        print(f"LaTeX files in: {latex_build_dir}")
                        print("You can manually build PDF using a LaTeX distribution")
                        return True
                        
                except FileNotFoundError:
                    print("pdflatex not found. LaTeX files generated but PDF not built.")
                    print(f"LaTeX files in: {latex_build_dir}")
                    print("To build PDF manually:")
                    print(f"  cd \"{latex_build_dir}\"")
                    print(f"  pdflatex cmeta-{version}.tex")
                    print(f"  pdflatex cmeta-{version}.tex  # Run twice for cross-references")
                    return True
            else:
                print("LaTeX main file not found")
                return False
                
        except Exception as e:
            print(f"Error running Sphinx LaTeX build: {e}")
            return False

    def _copy_pdfs_to_html_dirs(self, versioned_pdf_file, generic_pdf_file, version):
        """Copy PDF files to HTML directories for easy access.
        
        Args:
            versioned_pdf_file: Path to the versioned PDF (e.g., cmeta-0.0.1.pdf)
            generic_pdf_file: Path to the generic PDF (cmeta.pdf)
            version: Version string
        """
        html_build_dir = self.build_dir / "html"
        versioned_html_dir = html_build_dir / f"v{version}"
        
        # Copy only generic PDF to main HTML directory
        if html_build_dir.exists():
            try:
                dest_generic = html_build_dir / "cmeta.pdf"
                
                if generic_pdf_file.exists():
                    shutil.copy2(generic_pdf_file, dest_generic)
                    print(f"PDF copied to HTML: {dest_generic}")
                    
            except Exception as e:
                print(f"Warning: Could not copy PDF to main HTML directory: {e}")
        
        # Copy only generic PDF to versioned HTML directory
        if versioned_html_dir.exists():
            try:
                dest_generic = versioned_html_dir / "cmeta.pdf"
                
                if generic_pdf_file.exists():
                    shutil.copy2(generic_pdf_file, dest_generic)
                    print(f"PDF copied to versioned HTML: {dest_generic}")
                    
            except Exception as e:
                print(f"Warning: Could not copy PDF to versioned HTML directory: {e}")

    def _copy_existing_pdfs_to_html(self, version):
        """Copy any existing PDFs to HTML directories.
        
        Args:
            version: Version string
        """
        latex_build_dir = self.build_dir / "latex"
        
        if latex_build_dir.exists():
            versioned_pdf = latex_build_dir / f"cmeta-{version}.pdf"
            generic_pdf = latex_build_dir / "cmeta.pdf"
            
            if versioned_pdf.exists() or generic_pdf.exists():
                self._copy_pdfs_to_html_dirs(versioned_pdf, generic_pdf, version)


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description="Generate cMeta API documentation")
    parser.add_argument("--build", action="store_true", help="Build HTML documentation after generating RST files")
    parser.add_argument("--pdf", action="store_true", help="Build PDF documentation after generating RST files")
    parser.add_argument("--all", action="store_true", help="Build both HTML and PDF documentation")
    parser.add_argument("--clean", action="store_true", help="Clean build directory before generating documentation")
    parser.add_argument("--docs-dir", type=str, help="Path to docs directory (default: directory containing this script)")
    parser.add_argument("--cmeta-dir", type=str, help="Path to cMeta")
    parser.add_argument("--site-dir", type=str, help="Path to site")
    parser.add_argument("--site-cmeta-cref", type=str, help="Path to site")
     
    args = parser.parse_args()
    
    # Initialize builder
    docs_dir = Path(args.docs_dir) if args.docs_dir else None
    cmeta_dir = docs_dir.parent / "cmeta" if args.cmeta_dir is None else Path(args.cmeta_dir)
    site_dir = docs_dir / "site" if args.site_dir is None else Path(args.site_dir)

    builder = CMataDocBuilder(docs_dir, cmeta_dir, site_dir)
    
    try:
        # Clean if requested
        if args.clean:
            builder.clean_build_dir()
        
        # Generate documentation
        success = builder.generate_documentation()
        
        if not success:
            print("Failed to generate documentation")
            return 1
        
        # Build formats as requested
        build_success = True
        
        # Build HTML if requested or if this is the default
        if args.build or args.all or (not args.pdf):
            if not builder.build_html():
                print("Failed to build HTML documentation")
                build_success = False
        
        # Build PDF if requested
        if args.pdf or args.all:
            if not builder.build_pdf():
                print("Failed to build PDF documentation")
                build_success = False
        
        if not build_success:
            return 1
        
        # Show help for manual building
        if not (args.build or args.pdf or args.all):
            print("\nTo build documentation formats:")
            print(f"  HTML: python {Path(__file__).name} --build")
            print(f"  PDF:  python {Path(__file__).name} --pdf")
            print(f"  Both: python {Path(__file__).name} --all")
            print("or")
            print(f"  sphinx-build -b html {builder.docs_dir} {builder.build_dir / 'html'}")
            print(f"  sphinx-build -b latex {builder.docs_dir} {builder.build_dir / 'latex'}")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
