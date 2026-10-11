"""
Network functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import json
import os
import re

from .common import _error

# download(resume=True): the record kept next to a partly downloaded file, "<file>.resume" - where the
# bytes came from (url), what identified the file on the server (etag, last_modified) and its size
# (total). It is written before the first byte of a download and removed when the file is complete.
RESUME_RECORD_SUFFIX = '.resume'

##################################################################################################
def _resume_validator(
    record: dict,  # The resume record of a partly downloaded file.
):
    """
        The value for the If-Range header of a range request that continues a download: the strong
        ETag of the file on the server, else its Last-Modified date, else None (nothing proves that
        the rest would belong to the same file, so the download starts over).

        A weak ETag (W/"...") does not identify the bytes, and HTTP does not allow a date in its
        place (RFC 9110, 13.1.5): None for it too.

        Args:
            record (dict): The resume record of a partly downloaded file.

        Returns:
            str | None: The validator, or None when a continued download cannot be checked.
    """
    etag = record.get('etag')
    if etag:
        if isinstance(etag, str) and not etag.startswith('W/'):
            return etag
        return None

    last_modified = record.get('last_modified')
    if isinstance(last_modified, str) and last_modified:
        return last_modified

    return None

##################################################################################################
def _read_resume_record(
    path: str,  # Path of the resume record ("<file>.resume").
):
    """
        Read the resume record of a partly downloaded file.

        Args:
            path (str): Path of the resume record.

        Returns:
            dict | None: The record, or None when there is none or it cannot be used (unreadable,
                         cut by a crash, of another format): the download then starts over.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None

    if not isinstance(record, dict) or not isinstance(record.get('url'), str):
        return None

    total = record.get('total')
    if total is not None and (isinstance(total, bool) or not isinstance(total, int) or total < 0):
        return None

    return record

##################################################################################################
def _remove_file(
    path: str,  # File to remove.
):
    """
        Remove a file that may not exist.

        Args:
            path (str): File to remove.
    """
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

##################################################################################################
def _content_range(
    value: str,  # Value of a Content-Range header.
):
    """
        Parse a Content-Range header: "bytes 100-999/1000", "bytes 100-999/*" or "bytes */1000".

        Args:
            value (str | None): Value of the header.

        Returns:
            tuple | None: (first byte, last byte, total), each None when the header does not give it;
                          None when there is no header or it is not a byte range.
    """
    if not value:
        return None

    m = re.match(r'\s*bytes\s+(?:(\d+)\s*-\s*(\d+)|\*)\s*/\s*(\d+|\*)\s*$', str(value), re.IGNORECASE)
    if not m:
        return None

    first = int(m.group(1)) if m.group(1) is not None else None
    last = int(m.group(2)) if m.group(2) is not None else None
    total = int(m.group(3)) if m.group(3) != '*' else None

    return (first, last, total)

##################################################################################################
def access_api(
    url: str,  # The API endpoint URL.
    params: dict,  # Dictionary of parameters to send as JSON in the POST request body.
    headers: dict = {},  # Optional dictionary of HTTP headers to include in the request.
    timeout: int = 30,  # Request timeout in seconds. Default is 30 seconds.
):
    """
        Send POST request to FastAPI endpoint with JSON params and return response.

        Args:
            url (str): The API endpoint URL.
            params (dict): Dictionary of parameters to send as JSON in the POST request body.
            headers (dict): Optional dictionary of HTTP headers to include in the request.
            timeout (int): Request timeout in seconds. Default is 30 seconds.

        Returns:
            dict: Dictionary with 'return': 0 and 'response' containing parsed JSON response,
                  or 'return': 1 and 'error' message on failure.

        Raises:
            Exception: Propagated runtime errors, if any.
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

##################################################################################################
def download(
    url: str,  # URL of the file to download.
    filename: str = None,  # Name for the downloaded file. If None, extracts from URL.
    path: str = None,  # Directory to save the file. If None, uses current working directory.
    chunk_size: int = 65536,  # Size of chunks to download in bytes.
    show_progress: bool = False,  # If True, displays download progress using tqdm.
    fail_on_error: bool = False,  # If True, raises exception on error instead of returning error dict.
    text: str = 'Downloading ',  # Prefix text for progress bar description.
    headers: dict = None,  # Optional HTTP headers.
    api_key: str = None,  # API key added as X-API-Key header.
    skip_ssl_certificate: bool = False,  # If True, disables SSL certificate verification.
    space: str = '',  # Optional indentation prefix for console output formatting.
    resume: bool = False,  # If True, continues a partly downloaded file left by an earlier call.
):
    """
        Download a file from URL to local filesystem.

        Auto-detects filename from URL if not provided. Supports progress display
        with tqdm if show_progress is enabled.

        The transfer is checked against the size the server announced (Content-Length): a
        connection that ends before it is an error ('incomplete': True, with 'size' = the bytes
        on disk and 'total_size'), never a short file reported as downloaded. The bytes received
        stay in the file.

        With resume=True a file left by an earlier interrupted call is continued instead of
        started over: the bytes on disk are kept and the rest is asked for with an HTTP range
        request, on the condition (If-Range) that the file on the server is still the one the
        first bytes came from - its ETag or Last-Modified date, recorded next to the partial
        file in "<file>.resume". The download starts over whenever that cannot be guaranteed:
        no record, another URL, a server that names no such validator or does not serve ranges,
        a file that changed. A partial file is replaced only when the answer to replace it with
        has arrived. The record is removed when the file is complete.

        Args:
            url (str): URL of the file to download.
            filename (str | None): Name for the downloaded file. If None, extracts from URL.
            path (str | None): Directory to save the file. If None, uses current working directory.
            chunk_size (int): Size of chunks to download in bytes.
            show_progress (bool): If True, displays download progress using tqdm.
            fail_on_error (bool): If True, raises exception on error instead of returning error dict.
            text (str): Prefix text for progress bar description.
            headers (dict | None): Optional HTTP headers.
            api_key (str | None): API key added as X-API-Key header.
            skip_ssl_certificate (bool): If True, disables SSL certificate verification.

            space (str): Optional indentation prefix for console output formatting.
            resume (bool): If True, continues a partly downloaded file left by an earlier call.
        Returns:
            dict: Dictionary with 'return': 0, 'filename', 'path', 'size' (of the file) and
                  'resumed_from' (the bytes kept from an earlier call, 0 for a full download)
                  on success, or 'return': 1 and 'error' on failure.

        Raises:
            Exception: Propagated runtime errors, if any.
    """
    import ssl
    from urllib.parse import urlparse
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError

    if not url:
        return _error('url is required', fail_on_error=fail_on_error)

    tqdm_cls = None
    if show_progress:
        try:
            from tqdm import tqdm as tqdm_cls
        except ImportError as e:
            return _error(
                'tqdm package is required when show_progress is True',
                exception=e,
                fail_on_error=fail_on_error
            )

    downloaded = 0     # bytes received by this call
    start = 0          # bytes kept from an earlier call (resume)
    expected = None    # bytes this call is to receive, when the server says
    total_size = None  # size of the whole file, when known

    try:
        path = os.path.abspath(path) if path else os.getcwd()
        os.makedirs(path, exist_ok=True)

        if not filename:
            path_part = urlparse(url).path.rstrip('/')
            filename = os.path.basename(path_part) or 'downloaded-file'

        target_path = os.path.join(path, filename)
        resume_path = target_path + RESUME_RECORD_SUFFIX

        xheaders = headers.copy() if headers else {}
        xheaders.setdefault('User-Agent', 'Wget/1.21.3')
#        xheaders.setdefault('User-Agent', 'Mozilla/5.0')
        xheaders.setdefault('Connection', 'keep-alive')
        xheaders.setdefault('Accept', '*/*')
        xheaders.setdefault('Accept-Encoding', 'identity')

        if api_key:
            xheaders['X-API-Key'] = api_key

        ssl_context = None
        if skip_ssl_certificate:
            ssl_context = ssl._create_unverified_context()

        # A caller that asks for a range of its own gets exactly that range
        if resume and any(str(k).lower() in ('range', 'if-range') for k in xheaders):
            resume = False

        record = None
        validator = None
        known_total = None

        if resume:
            # What an earlier call left: continue only a partial file of this URL whose origin can be checked
            record = _read_resume_record(resume_path)
            try:
                on_disk = os.path.getsize(target_path)
            except OSError:
                on_disk = 0

            if record is not None and record['url'] == url and on_disk > 0:
                validator = _resume_validator(record)
                known_total = record.get('total')

                if validator and (known_total is None or on_disk <= known_total):
                    if known_total is not None and on_disk == known_total:
                        # Every announced byte is on disk: the earlier call was stopped after its last write
                        _remove_file(resume_path)
                        return {
                            'return': 0,
                            'filename': filename,
                            'path': target_path,
                            'size': on_disk,
                            'resumed_from': on_disk
                        }

                    start = on_disk

        response = None
        content_range = None

        for _request in (1, 2):
            request_headers = dict(xheaders)
            if start > 0:
                request_headers['Range'] = f'bytes={start}-'
                request_headers['If-Range'] = validator

            try:
                response = urlopen(Request(url, headers=request_headers), context=ssl_context)
            except HTTPError as e:
                if start == 0:
                    raise

                # The range request was refused. 416 with the size on disk: the file is complete already.
                # Anything else: one request for the whole file - a server that fails on ranges must not
                # make the same download fail for ever (the partial file is untouched until that answer comes).
                complete = False
                if e.code == 416:
                    refused = _content_range(e.headers.get('Content-Range') if e.headers is not None else None)
                    complete = refused is not None and refused[2] == start
                e.close()

                if complete:
                    _remove_file(resume_path)
                    return {
                        'return': 0,
                        'filename': filename,
                        'path': target_path,
                        'size': start,
                        'resumed_from': start
                    }

                start = 0
                continue

            # HTTP responses have getheader(); a file:// response (urllib's addinfourl) has headers only
            response_headers = getattr(response, 'headers', None)

            if start > 0:
                # The rest of the same file is a 206 that starts where the file on disk ends, for a file of
                # the size and with the validator recorded. A 200 is the whole file (the server does not
                # serve ranges, or the file changed): it replaces the partial one. A 206 of anything else
                # cannot be used: the whole file is asked for.
                status = getattr(response, 'status', None)
                content_range = _content_range(response_headers.get('Content-Range') if response_headers is not None else None) \
                    if status == 206 else None

                same_file = content_range is not None and content_range[0] == start \
                    and (known_total is None or content_range[2] is None or content_range[2] == known_total)

                if same_file and response_headers is not None:
                    answered = response_headers.get('ETag') if validator == record.get('etag') else response_headers.get('Last-Modified')
                    same_file = answered is None or answered == validator

                if not same_file:
                    start = 0
                    content_range = None
                    if status == 206:
                        response.close()
                        response = None
                        continue

            break

        if response is None:
            raise RuntimeError('no answer to the request for the whole file')

        with response:
            response_headers = getattr(response, 'headers', None)
            length = response_headers.get('Content-Length') if response_headers is not None else None
            try:
                length = int(length) if length is not None else None
            except (TypeError, ValueError):
                length = None

            expected = length

            if start > 0:
                if content_range[2] is not None:
                    total_size = content_range[2]
                elif length is not None:
                    total_size = start + length
                else:
                    total_size = known_total
            else:
                total_size = length
                if resume:
                    # The record of an earlier partial file never describes the bytes that follow
                    _remove_file(resume_path)

            with open(target_path, 'ab' if start > 0 else 'wb') as out_file:
                if resume and start == 0:
                    new_record = {
                        'url': url,
                        'etag': response_headers.get('ETag') if response_headers is not None else None,
                        'last_modified': response_headers.get('Last-Modified') if response_headers is not None else None,
                        'total': total_size
                    }
                    if _resume_validator(new_record):
                        with open(resume_path, 'w', encoding='utf-8') as f:
                            json.dump(new_record, f)

                progress = (
                    tqdm_cls(
                        total=total_size,
                        initial=start,
                        unit='B',
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=space + text + filename
                    ) if tqdm_cls else None
                )

                try:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        downloaded += len(chunk)
                        # tqdm without a total (no Content-Length) refuses bool(): compare with None
                        if progress is not None:
                            progress.update(len(chunk))
                finally:
                    if progress is not None:
                        progress.close()

    except Exception as e:
        return _error(
            f'Failed to download {url}',
            exception=e,
            fail_on_error=fail_on_error
        )

    # http.client returns the bytes it got when the connection ends early and raises nothing (a read with
    # a size): without this check a cut transfer was a short file reported as downloaded
    if (expected is not None and downloaded < expected) or (total_size is not None and start + downloaded < total_size):
        if total_size is None:
            total_size = start + expected
        return _error(
            f'Failed to download {url}: the connection ended after {start + downloaded} of {total_size} bytes',
            fail_on_error=fail_on_error,
            extra={'incomplete': True, 'size': start + downloaded, 'total_size': total_size}
        )

    if resume:
        _remove_file(resume_path)

    return {
        'return': 0,
        'filename': filename,
        'path': target_path,
        'size': start + downloaded,
        'resumed_from': start
    }

##################################################################################################
async def unify_request(
    request,  # Value for request.
):
    """
        Merge query and JSON-body parameters into one normalized dictionary.

        Args:
            request: Value for request.
        Returns:
            dict: Operation result.
        Raises:
            Exception: Propagated runtime errors, if any.
    """

    # Get query parameters
    query_params = dict(request.query_params)

    body_dict = {}

    if request.method == "POST":
        # Read the raw body once. It can fail when the client went away while sending
        # (a page reloaded or closed while an AJAX call was in flight) - report it,
        # never raise: the caller turns 'return' > 0 into an HTTP error answer.
        try:
           raw = await request.body()
        except Exception as e:
           return {'return':99, 'error':'the POST body could not be read: ' + format(e)}

        # An empty body means "no extra parameters" (e.g. `curl -X POST <url>` without
        # -d, or a client that sends the parameters in the query string only).
        if raw is not None and len(raw.strip()) > 0:
            try:
               body_dict = json.loads(raw)
            except Exception as e:
               return {'return':99, 'error':'the POST body is not valid JSON: ' + format(e)}

            if not isinstance(body_dict, dict):
               return {'return':99, 'error':'the POST body must be a JSON object, not ' + type(body_dict).__name__}

        query = {**query_params, **body_dict}
    else:
        query = query_params

    return {'return':0, 'query': query}
