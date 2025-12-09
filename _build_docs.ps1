$ErrorActionPreference = "Stop"

try {
    # Run cx and capture output + exit code
    $raw = cx docs get cmeta-api-auto,e2d0f4afcc20470a --show-path 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "cx command failed:`n$raw"
        exit $LASTEXITCODE
    }

    # Take last non-empty line as path
    $CMETA_DOCS = $raw
    Write-Output "Using CMETA_DOCS = $CMETA_DOCS"

    # Run the rest of the commands
    uv pip install -r docs/requirements.txt

    uv run python docs/build_docs.py --build `
        --docs-dir "$($PWD.Path)/docs/en" `
        --cmeta-dir "$($PWD.Path)/cmeta" `
        --site-dir "$CMETA_DOCS/site"
}
catch {
    Write-Error "Script stopped due to an error: $_"
    exit 1
}
