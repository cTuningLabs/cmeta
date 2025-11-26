"""
Network functions

cMeta author and developer: (C) 2025 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

def access_api(url, params, headers = {}):
    """
    Send POST request to FastAPI endpoint with params and return JSON response.
    
    Parameters:
        url (str): The API endpoint URL
        params (dict): Dictionary of parameters to send as JSON
        
    Returns:
        dict: {'return': 0, 'output': dict} on success
              {'return': 1, 'error': str} on error
    """
    import requests

    try:
        response = requests.post(url, json=params, headers=headers)
        response.raise_for_status()
        
        output = response.json()
       
    except requests.exceptions.RequestException as e:
        return {'return': 1, 'error': f'API request to {url} failed: {str(e)}'}
    except ValueError as e:
        return {'return': 1, 'error': f'Failed to parse JSON response from {url}: {str(e)}'}
    except Exception as e:
        return {'return': 1, 'error': f'Unexpected error when accessing {url}: {str(e)}'}

    return {'return': 0, 'response': output}



def download(url, filename=None, path=None, chunk_size=65536, show_progress=False, fail_on_error=False, text="Downloading "):
    """
    Download a file from URL into path/filename, auto-detecting missing pieces.
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

