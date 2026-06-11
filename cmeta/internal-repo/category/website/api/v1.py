"""
cMeta website functions

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import os
import shutil
import glob
from copy import deepcopy

from cmeta.category import InitCategory

class Category(InitCategory):
    """
    Managing websites
    """

#    def __init__(self, *kwargs):
#        self.module_file_path = __file__
#        super().__init__(*kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, module_file_path = __file__, **kwargs)

    ############################################################
    def build_(self, 
        ctx, 
        arg1, 
        subdir=None,
        ignore_dirs=None,
    ):
        """
        Build website

        Args:
            ctx (dict): cMeta context.
            arg1 (str): cMeta artifact with a website directory


        Returns:
            dict: A cMeta return dictionary with the following keys:
                - "return" (int): 0 if successful, or error code otherwise.
                - "error" (str): Error message if "return" > 0.
                - "artifacts" (list): List of cMeta artifacts.
        """

        con = ctx['control'].get('con', False)

        # Call base find function to find an artifact with a website
        p = self._prepare_input_from_ctx(ctx, base = True)

        p['command'] = 'find'
        p['con'] = False
        p['arg1'] = arg1

        r = self.cm.access(p)
        if r['return']>0: return r

        artifacts = r['artifacts']

        if len(artifacts)>1:
            category_str = ctx['category']['artifact_alias']
            return {'return':1, 'error': f'more than 1 artifact found for "{category_str}" - please specify one'}

        # Path to artifact
        path = artifacts[0]['path']
        artifact_path = path

        if subdir != None:
            path = os.path.join(path, subdir)

        if con:
            print (f'Website path: {path}')

        # Check and load _build.json or _build.yaml
        build_file = os.path.join(path, '_build')

        r = self.cm.utils.files.safe_read_yaml_or_json(build_file, fail_on_error=self.fail_on_error)
        if r['return']>0: return r

        build_filepath = r['filepath']

        if con:
            print (f'Build meta file: {build_filepath}')

        build_data = r['data']

        # Check template

        template_file = build_data['template_file']

        template_filepath = os.path.join(path, template_file)

        r = self.cm.utils.files.safe_read_file(template_filepath, fail_on_error=self.fail_on_error)
        if r['return']>0: return r

        html = r['data'] 
        vars = build_data.get('vars', {})

        # Check if _build.tmp exists, delete and recreate
        build_tmp_path = os.path.join(artifact_path, '_build.tmp')
        
        if os.path.exists(build_tmp_path):
            shutil.rmtree(build_tmp_path)
        
        os.makedirs(build_tmp_path)

        if con:
            print(f'Build tmp directory: {build_tmp_path}')

        if not ignore_dirs:
            ignore_dirs = []

        # Get all *.html files in path and subdirectories
#        html_files = glob.glob(os.path.join(path, '**', '*.html'), recursive=True)

        html_files = []

        for root, dirs, files in os.walk(path):
            # Skip traversing ignored directories
            dirs[:] = [d for d in dirs if d not in ignore_dirs]

            for f in files:
                if f.endswith('.html'):
                    html_files.append(os.path.join(root, f))


        # Filter out files in directories starting with underscore
        filtered_html_files = []
        for html_file in html_files:
            rel_path = os.path.relpath(html_file, path)
            path_parts = rel_path.split(os.sep)
            
            # Check if any directory in the path starts with underscore
            skip_file = False
            for part in path_parts[:-1]:  # Exclude the filename itself
                if part.startswith('_'):
                    skip_file = True
                    break
            
            if not skip_file:
                filtered_html_files.append(html_file)

        for html_file in filtered_html_files:
            html_filename = os.path.basename(html_file)
            
            # Calculate relative path from base path
            rel_path = os.path.relpath(html_file, path)
            rel_dir = os.path.dirname(rel_path)
            
            if con:
                print(f'* Processing: {rel_path}')
            
            # Create subdirectory in build_tmp_path if needed
            if rel_dir and rel_dir != '.':
                output_dir = os.path.join(build_tmp_path, rel_dir)
                os.makedirs(output_dir, exist_ok=True)
                output_file_path = os.path.join(output_dir, html_filename)
            else:
                output_file_path = os.path.join(build_tmp_path, html_filename)
            
            # Check for associated yaml or json
            base_name = os.path.splitext(html_file)[0]
            
            r = self.cm.utils.files.safe_read_yaml_or_json(base_name, fail_on_error=False)
            
            if r['return'] > 0 or not r.get('filepath'):
                # No metadata file, just copy HTML
                shutil.copy(html_file, output_file_path)
            else:
                # Load metadata
                page_meta = r['data']

                # Load page HTML
                r = self.cm.utils.files.safe_read_file(html_file, fail_on_error=self.fail_on_error)
                if r['return'] > 0: return r
                
                page_html = r['data']
                
                # Check if raw
                if page_meta.get('raw', False):
                    result_html = page_html
                    
                else:
                    # Check if page has its own template
                    page_html_to_use = html
                    if 'template_file' in page_meta:
                        page_template_file = page_meta['template_file']
                        page_template_filepath = os.path.join(path, page_template_file)
                        
                        r = self.cm.utils.files.safe_read_file(page_template_filepath, fail_on_error=self.fail_on_error)
                        if r['return'] > 0: return r
                        
                        page_html_to_use = r['data']

                    # Substitute cx_body
                    result_html = page_html_to_use.replace('{{cx_body}}', page_html)
                
                # Deep copy vars and merge with page_meta vars
                merged_vars = deepcopy(vars)
                merged_vars.update(page_meta.get('vars', {}))
                
                # Substitute all vars
                for var, value in merged_vars.items():
                    result_html = result_html.replace(f'{{{{{var}}}}}', str(value))
                
                # Write to _build.tmp with proper path
                r = self.cm.utils.files.safe_write_file(output_file_path, result_html, fail_on_error=self.fail_on_error)
                if r['return'] > 0: return r

        return {'return':0}
