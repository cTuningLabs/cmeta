# CMeta Documentation

This directory contains the Sphinx documentation for the cMeta project. 
The documentation is automatically generated from the Python source code 
and provides comprehensive API reference for all classes and functions.

## Quick Start

The easiest way to build the documentation is using the setup script:

```bash
# Install dependencies and build complete documentation
python setup_docs.py

# Or step by step:
python setup_docs.py --install-deps  # Install Sphinx and dependencies
python setup_docs.py --generate-only # Generate RST files from source
python setup_docs.py --build-only    # Build HTML documentation
```

## Manual Building

### Prerequisites

Install the required dependencies:

```bash
pip install -r requirements-docs.txt
```

### Generate Documentation

1. **Generate RST files from Python source:**
   ```bash
   python build_docs.py
   ```

2. **Build HTML documentation:**
   ```bash
   python build_docs.py --build
   ```

3. **Or do both in one step:**
   ```bash
   python build_docs.py --build
   ```

### Using Make (Optional)

If you have `make` available:

```bash
# Install dependencies
make install-deps

# Generate RST files
make generate

# Generate and build complete documentation
make docs

# Clean build directory
make clean
```

On Windows, you can use the batch file:

```cmd
# Generate and build documentation
make.bat docs

# Clean build directory  
make.bat clean
```

## File Structure

```
docs/
├── conf.py                 # Sphinx configuration
├── build_docs.py          # Main documentation generator
├── setup_docs.py          # Easy setup and build script
├── requirements-docs.txt  # Documentation dependencies
├── Makefile               # Make targets for Unix systems
├── make.bat               # Batch file for Windows
├── README.md              # This file
├── api/                   # Generated API documentation
│   ├── index.rst          # API reference index
│   └── *.rst              # Generated module documentation
├── _build/                # Built documentation (generated)
│   └── html/              # HTML output
├── _static/               # Static files (CSS, JS, images)
└── _templates/            # Custom Sphinx templates
```

## Configuration

The Sphinx configuration is in `conf.py`. Key settings:

- **Theme**: Uses `sphinx_rtd_theme` (Read the Docs theme)
- **Extensions**: Includes autodoc, napoleon, viewcode, and others
- **Auto-discovery**: Automatically finds and documents all modules in the `cmeta` package

## Generated Documentation

The documentation includes:

- **Main CMeta class** (`cmeta.core.CMeta`) - The primary interface
- **Configuration management** (`cmeta.config.Config`)
- **Repository management** (`cmeta.repos.Repos`) 
- **Utility functions** (`cmeta.utils`)
- **Version information** (`cmeta.version`)

## Viewing Documentation

After building, open the documentation in your browser:

- **Local file**: `_build/html/index.html`
- **Full path**: `file:///{absolute_path_to_docs}/_build/html/index.html`

## Troubleshooting

### Common Issues

1. **ImportError when generating docs:**
   - Ensure the `cmeta` package is properly installed or accessible
   - Check that all dependencies are installed

2. **Sphinx build errors:**
   - Check the syntax of generated RST files in the `api/` directory
   - Verify that all imported modules are available

3. **Missing dependencies:**
   - Run `pip install -r requirements-docs.txt`
   - Ensure you're using a compatible Python version (3.7+)

### Clean Rebuild

To perform a clean rebuild:

```bash
python build_docs.py --clean
python build_docs.py --build
```

Or using make:

```bash
make clean
make docs
```

## Advanced Usage

### Custom Build Directory

You can specify a custom docs directory:

```bash
python build_docs.py --docs-dir /path/to/custom/docs
```

### Integration with CI/CD

The scripts are designed to work in automated environments:

```bash
# In a CI/CD pipeline
python setup_docs.py --install-deps
python setup_docs.py --generate-only
python setup_docs.py --build-only
```

## Contributing

When adding new modules or classes to CMeta:

1. Ensure proper docstrings following Google or NumPy style
2. Run the documentation generator to verify the new code is included
3. Check that the generated documentation renders correctly

The documentation generator automatically discovers new modules, so no manual configuration is typically needed.
