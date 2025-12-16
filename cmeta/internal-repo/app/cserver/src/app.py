"""
Minimal cMeta server

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import subprocess
import argparse
import os
import mimetypes

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import uvicorn

app = FastAPI()

script_path = os.path.abspath(__file__)
home_dir = os.path.basename(os.path.dirname(script_path))

home_dir_templates = os.path.join(home_dir, 'templates')
templates = Jinja2Templates(directory = home_dir_templates)

home_dir_static = os.path.join(home_dir, 'static')
app.mount('/static', StaticFiles(directory = home_dir_static), name="static")

##################################################################################################
# Prepare cMeta
from cmeta.core_async import CMetaAsync

cpu_count = os.cpu_count()

max_workers = int (cpu_count * 0.8 + 0.5)

cm = CMetaAsync(max_workers = max_workers, debug = False)



##################################################################################################
@app.get("/")
async def home(request: Request):
    r = await cm.utils.net.unify_request(request)
    if r['return']>0: return r

    query = r['query']

    txt = f'Welcome to the cMeta server v{cm.__version__}!'

    out = query.get('out', '')
    if out == 'json':
        return JSONResponse(content = {'return': 0, 'text': txt})
    else:
        html_meta = {'request': request, 'html': f'<h3>{txt}</h3>'}
        return templates.TemplateResponse('task.html', html_meta, status_code = 200)


##################################################################################################
@app.get("/favicon.ico")
async def favicon():
    return FileResponse(os.path.join(home_dir_static, "images", "favicon.ico"))

##################################################################################################
##################################################################################################
@app.api_route("/{task}", methods=["GET", "POST"], response_class=HTMLResponse)
@app.api_route("/{task}/", methods=["GET", "POST"], response_class=HTMLResponse)
async def task_handler(request: Request, task: str):

    r = await cm.utils.net.unify_request(request)
    if r['return']>0: return r

    query = r['query']

    url = str(request.url_for("task_handler", task=task)) + '?'
    url_server = str(request.url_for("home"))
    url_server_js_script = url_server + 'static/js/cmeta_server.js'
    url_files = str(request.url_for("task_handler", task=task))
    if not url_files.endswith('/'): url_files += '/'

    command = query.get('command', '')
    if command is None or command.strip() == '':
        command = 'web'

    cmeta_params = {'category':f'cserver.{task}',
                    'command':command}

    cmeta_params['urls'] = {
        'url': url,
        'url_files': url_files,
        'url_server': url_server,
        'url_server_js_script': url_server_js_script,
    }

    cmeta_params['query'] = query

    r = await cm.access(cmeta_params)
    if r['return']>0: 
        html_meta = {"message": r['error'], 'request': request}
        return templates.TemplateResponse('error.html', html_meta, status_code = 200)

    if 'json' in r:
        return JSONResponse(content = r['json'])

    html_meta = r.get('html_meta',{})

    html_meta['request'] = request

    return templates.TemplateResponse('task.html', html_meta, status_code = 200)

##################################################################################################
@app.get("/{task}/{file_path:path}")
async def task_files(request: Request, task: str, file_path: str):
    # Forbid relative paths
    if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Relative paths are not allowed")

    task_name = f'cserver.{task}'

    r = await cm.access({'category': 'category',
                         'command': 'find',
                         'arg1': task_name})
    if r['return'] > 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to find category {task_name}")  

    artifacts = r['artifacts']

    if len(artifacts) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cmeta artifact for files not found")
    elif len(artifacts) > 1:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Multiple cmeta artifacts found for files")   

    artifact = artifacts[0]

    project_files_path = artifact['path']
    project_files_path = os.path.join(project_files_path, 'files')

    full_file_path = os.path.join(project_files_path, file_path)

    # Prevent directory traversal
    try:
        full_file_path = os.path.abspath(full_file_path)
        project_files_path = os.path.abspath(project_files_path)
        if not full_file_path.startswith(project_files_path):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid file path")
    except Exception as e:
        logger.error(f"Path validation error: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")

    # Check if file exists
    if os.path.isdir(full_file_path):
        full_file_path_to_index = os.path.join(full_file_path, 'index.html')
        if os.path.isfile(full_file_path_to_index):
            full_file_path = full_file_path_to_index

    if not os.path.isfile(full_file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Determine media type
    media_type, _ = mimetypes.guess_type(full_file_path)
    if media_type is None:
        media_type = 'application/octet-stream'

    if media_type == 'text/html':
        html_meta['request'] = request

        return templates.TemplateResponse('task.html', html_meta, status_code = 200)

    return FileResponse(full_file_path, media_type=media_type)
