# Sphinx Documentation Configuration for FastAPI Integration

## What Was Changed

Your Sphinx documentation has been configured to work seamlessly with your dark-themed FastAPI project:

### 1. **Custom Dark Theme CSS** (`en/_static/custom.css`)
   - Dark color scheme matching common dark themes
   - All styles are scoped to `.sphinx-docs-container` to prevent conflicts with your base HTML
   - Colors: Dark backgrounds (#1e1e1e, #2d2d30) with light text (#e8e6e3)
   - Styled code blocks, tables, links, and navigation for dark mode

### 2. **Custom Layout Template** (`en/_templates/layout.html`)
   - Wraps all Sphinx content in a `<div class="sphinx-docs-container">` 
   - Resets body styles using `all: initial` to prevent interference with your FastAPI app
   - Prevents Sphinx's theme classes from affecting your parent page

### 3. **Updated Configuration** (`en/conf.py`)
   - Added `html_css_files` to load custom CSS
   - Configured theme options for better embedding
   - Added template path for custom layout
   - Disabled some unnecessary elements (Sphinx branding)

## How to Use in Your FastAPI Project

### Option 1: Serve the Entire HTML Files
```python
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Mount static files
app.mount("/docs/static", StaticFiles(directory="docs/site/en/html/_static"), name="docs-static")

@app.get("/docs/{path:path}")
async def serve_docs(path: str):
    if not path:
        path = "index.html"
    return FileResponse(f"docs/site/en/html/{path}")
```

### Option 2: Extract and Embed Content Only
For better integration, extract just the content div from the generated HTML:

```python
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from bs4 import BeautifulSoup

app = FastAPI()
templates = Jinja2Templates(directory="templates")

def extract_sphinx_content(html_path: str):
    """Extract just the docs content from Sphinx HTML."""
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    
    # Extract the main content
    content = soup.find('div', class_='sphinx-docs-container')
    return str(content) if content else ""

@app.get("/docs/{path:path}")
async def serve_docs(request: Request, path: str = "index"):
    html_file = f"docs/site/en/html/{path}.html"
    content = extract_sphinx_content(html_file)
    
    return templates.TemplateResponse("base.html", {
        "request": request,
        "content": content
    })
```

### Option 3: Use as an iframe
```html
<iframe src="/sphinx-docs/index.html" 
        style="width: 100%; height: 100vh; border: none;">
</iframe>
```

## Rebuilding Documentation

After making these changes, rebuild your documentation:

```bash
python build_docs.py --clean --build
```

## Further Customization

### Change Color Scheme
Edit `en/_static/custom.css` and modify the color variables:
- `#1e1e1e` - Main background
- `#2d2d30` - Secondary background  
- `#e8e6e3` - Main text color
- `#5a9fd4` - Link color

### Alternative: Use Furo Theme (Modern Dark Theme)
If you want a more modern dark theme, install Furo:

```bash
pip install furo
```

Then update `en/conf.py`:
```python
html_theme = 'furo'
html_theme_options = {
    "dark_css_variables": {
        "color-brand-primary": "#5a9fd4",
        "color-brand-content": "#5a9fd4",
    },
}
```

### Remove the Container Wrapper
If you're using iframes or want full-page docs, you can remove the scoping by deleting `en/_templates/layout.html` and updating the CSS to remove `.sphinx-docs-container` prefixes.

## Troubleshooting

1. **Styles still conflicting**: Make sure your FastAPI template doesn't have CSS reset rules that override Sphinx styles
2. **Dark theme not showing**: Clear your browser cache and rebuild docs with `--clean`
3. **Static files not loading**: Ensure static file paths are correctly mounted in FastAPI

## Files Modified/Created
- ✅ Created: `en/_static/custom.css` (dark theme + scoped styles)
- ✅ Created: `en/_templates/layout.html` (scoped wrapper)
- ✅ Modified: `en/conf.py` (added theme config and custom files)
