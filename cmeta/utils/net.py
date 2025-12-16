"""
Network functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

from .common import _error

def access_api(
        url: str,         # The API endpoint URL
        params: dict,     # Dictionary of parameters to send as JSON
        headers: dict = {},  # Optional dictionary of HTTP headers
        timeout: int = 30    # Request timeout in seconds
):
    """Send POST request to FastAPI endpoint with JSON params and return response.
    
    Args:
        url (str): The API endpoint URL.
        params (dict): Dictionary of parameters to send as JSON in the POST request body.
        headers (dict): Optional dictionary of HTTP headers to include in the request.
        timeout (int): Request timeout in seconds. Default is 30 seconds.
        
    Returns:
        dict: Dictionary with 'return': 0 and 'response' containing parsed JSON response,
              or 'return': 1 and 'error' message on failure.
    """
    import requests

    try:
        response = requests.post(url, json=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        output = response.json()
       
    except requests.exceptions.RequestException as e:
        return {'return': 1, 'error': f'API request to {url} failed: {str(e)}'}
    except ValueError as e:
        return {'return': 1, 'error': f'Failed to parse JSON response from {url}: {str(e)}'}
    except Exception as e:
        return {'return': 1, 'error': f'Unexpected error when accessing {url}: {str(e)}'}

    return {'return': 0, 'response': output}



def download(
        url: str,                     # URL of the file to download
        filename: str = None,         # Name for the downloaded file
        path: str = None,             # Directory to save the file
        chunk_size: int = 65536,      # Size of chunks to download in bytes
        show_progress: bool = False,  # If True, display download progress
        fail_on_error: bool = False,  # If True, raise exception on error
        text: str = "Downloading "   # Prefix text for progress bar
):
    """Download a file from URL to local filesystem.
    
    Auto-detects filename from URL if not provided. Supports progress display
    with tqdm if show_progress is enabled.
    
    Args:
        url (str): URL of the file to download.
        filename (str | None): Name for the downloaded file. If None, extracts from URL.
        path (str | None): Directory to save the file. If None, uses current working directory.
        chunk_size (int): Size of chunks to download in bytes. Default is 65536 (64KB).
        show_progress (bool): If True, displays download progress using tqdm.
        fail_on_error (bool): If True, raises exception on error instead of returning error dict.
        text (str): Prefix text for progress bar description.
        
    Returns:
        dict: Dictionary with 'return': 0, 'filename', 'path', and 'size' on success,
              or 'return': 1 and 'error' on failure.
    """
    import os
    from urllib.parse import urlparse
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError

    if not url:
        return _error('url is required', fail_on_error=fail_on_error)

    tqdm_cls = None
    if show_progress:
        try:
            from tqdm import tqdm as tqdm_cls
        except ImportError as e:
            return _error('tqdm package is required when show_progress is True', exception=e, fail_on_error=fail_on_error)

    try:
        path = os.path.abspath(path) if path else os.getcwd()
        os.makedirs(path, exist_ok=True)

        if not filename:
            path_part = urlparse(url).path.rstrip('/')
            filename = os.path.basename(path_part) or 'downloaded-file'

        target_path = os.path.join(path, filename)
        request = Request(url, headers={'User-Agent': 'Mozilla/5.0'})

        with urlopen(request) as response, open(target_path, 'wb') as out_file:
            total_size = response.getheader('Content-Length')
            total_size = int(total_size) if total_size is not None else None
            downloaded = 0
            progress = tqdm_cls(total=total_size, unit='B', unit_scale=True, unit_divisor=1024, desc=text+filename) if tqdm_cls else None

            try:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress.update(len(chunk))
            finally:
                if progress:
                    progress.close()

    except (URLError, HTTPError, OSError) as e:
        return _error(f'Failed to download {url}', exception=e, fail_on_error=fail_on_error)

    return {'return': 0, 'filename': filename, 'path': target_path, 'size': downloaded}


##################################################################################################
async def unify_request(request):
    """
    """

    # Get query parameters
    query_params = dict(request.query_params)

    body_dict = {}

    headers = request.headers

    api_key = None
    username = None

    if request.method == "POST":
        try:
           body_dict = await request.json()
        except Exception as e:
           return {'return':99, 'error':format(e)}

        query = {**query_params, **body_dict}
    else:
        query = query_params

    return {'return':0, 'query': query}
