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
from starlette.middleware.sessions import SessionMiddleware

import uvicorn

app = FastAPI()

# Add session middleware with proper cookie settings
app.add_middleware(
    SessionMiddleware, 
    secret_key="cserver_secret_key_for_production",
    session_cookie="cserver_session",
    max_age=3600,  # 1 hour
    same_site="lax",
    https_only=False  # Set to True in production with HTTPS
)

script_path = os.path.abspath(__file__)
home_dir = os.path.basename(os.path.dirname(script_path))

home_dir_templates = os.path.join(home_dir, 'templates')
templates = Jinja2Templates(directory = home_dir_templates)

home_dir_static = os.path.join(home_dir, 'static')
app.mount('/static', StaticFiles(directory = home_dir_static), name="static")

##################################################################################################
# Prepare cMeta
from cmeta.core_async import CMetaAsync
from cmeta import catch as cmeta_catch

cpu_count = os.cpu_count()

max_workers = int (cpu_count * 0.8 + 0.5)

cm = CMetaAsync(max_workers = max_workers, debug = False)

##################################################################################################
# Get configuration

cfg = {}

@app.on_event("startup")
async def test_cmeta_repos():
    global cm, cfg
    r = await cm.access({'category':'config,cc6bfe174be847ed', 'command':'get', 'arg1':'cserver'})
    if r['return'] > 0: cmeta_catch(r)

    cfg = r['config_cmeta']

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

    force_json = query.get('force_json', False)

    # Check if API KEYS (very basic, native and insecure implementation just for testing)
    api_keys = cfg.get('api_keys', [])
    validated_api_key = None
    if len(api_keys)>0:
        err = ''
        api_key = query.get('api_key')
        if api_key is None or api_key == '':
            api_key = request.session.get('api_key')

        if api_key is None or api_key == '':
            err = 'api_key must be present in the query'
        else:
            if api_key not in api_keys:
                err = 'this api_key is not authorized'
            else:
                validated_api_key = api_key

        if err != '':
            r = {'return':1, 'error': err}

            if force_json:
               return JSONResponse(content = r)

            html_meta = {"message": r['error'], 'request': request}
            return templates.TemplateResponse('error.html', html_meta, status_code = 200)
        
        # Store validated API key in session
        request.session['api_key'] = validated_api_key

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
        if force_json:
            return JSONResponse(content = r)

        html_meta = {"message": r['error'], 'request': request}
        return templates.TemplateResponse('error.html', html_meta, status_code = 200)

    if 'json' in r:
        return JSONResponse(content = r['json'])

    html_meta = r.get('html_meta',{})

    html_meta['request'] = request

    if force_json:
        return JSONResponse(content = cm.utils.common.safe_serialize_json(r))

    return templates.TemplateResponse('task.html', html_meta, status_code = 200)

##################################################################################################
@app.get("/{task}/{file_path:path}")
async def task_files(request: Request, task: str, file_path: str):

    # Forbid relative paths
    if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Relative paths are not allowed")

    api_keys = cfg.get('api_keys', [])
    if len(api_keys)>0:
        # Check if API key exists in session
        api_key = request.session.get('api_key')
        
        # If not in session, check query parameter as fallback
        if api_key is None:
            api_key = request.query_params.get('api_key')
            if api_key is not None and api_key in api_keys:
                # Store in session for future requests
                request.session['api_key'] = api_key
        
        # Validate API key
        if api_key is None or api_key not in api_keys:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized access - invalid or missing API key")

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
        html_meta={'request': request}
        return templates.TemplateResponse('task.html', html_meta, status_code = 200)

    return FileResponse(full_file_path, media_type=media_type)
