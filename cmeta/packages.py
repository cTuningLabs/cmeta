"""
Package Manager class

cMeta author and developer: (C) 2025-2026 Grigori Fursin

See the cMeta COPYRIGHT and LICENSE files in the project root for details.
"""

import importlib
import subprocess
import sys
import threading
import os
import signal
from dataclasses import dataclass

from packaging import version as pkg_version
from packaging.specifiers import SpecifierSet

@dataclass
class PackageResult:
    module: object
    name: str
    version: str
    satisfies: bool
    specifier: str 
    installed_now: bool


class Packages:
    def __init__(
        self,
        cfg = None,  # Framework configuration dictionary.
        cache = None,  # Cache dictionary used to store resolved data.
        logger = None,  # Logger instance used for diagnostic messages.
        fail_on_error = False,  # If True, raise exceptions instead of returning error dictionaries.
        allow_install = True,  # If True, allow automatic package installation.
        timeout: float = None,  # Timeout value in seconds.
        add_install_args: str = None,  # Value for add install args.
    ):
        """
            Initialize package manager state and install/runtime options.

            Args:
                cfg: Framework configuration dictionary.
                cache: Cache dictionary used to store resolved data.
                logger: Logger instance used for diagnostic messages.
                fail_on_error: If True, raise exceptions instead of returning error dictionaries.
                allow_install: If True, allow automatic package installation.
                timeout (float): Timeout value in seconds.
                add_install_args (str): Value for add install args.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        self.cache = cache or {}
        self.cfg = cfg or {}
        self.cache_lock = threading.Lock()
        self.logger = logger
        self.fail_on_error = fail_on_error
        self.allow_install = allow_install
        self.default_timeout = timeout  # seconds or None
#        self.deps = deps or {}
        self.add_install_args = add_install_args

    # ------------------------------------------------------------------
    # Logging wrapper
    # ------------------------------------------------------------------
    def log(
        self,
        level,  # Log level string (e.g., 'debug', 'info', 'warning', 'error').
        msg,  # Message to log.
    ):
        """
            Log a message using the configured logger.

            Args:
                level: Log level string (e.g., 'debug', 'info', 'warning', 'error').
                msg: Message to log.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        if self.logger:
            fn = getattr(self.logger, level, None)
            if callable(fn):
                fn(msg)

    # ------------------------------------------------------------------
    # Version helpers
    # ------------------------------------------------------------------
    def get_version(
        self,
        module,  # Python module object.
    ):
        """
            Get version string from a Python module.

            Args:
                module: Python module object.
            Returns:
                str or None: Version string if available, None otherwise.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        if hasattr(module, "__version__"):
            return module.__version__
        try:
            from importlib.metadata import version
            return version(module.__name__)
        except Exception:
            return None

    def poetry_to_pep440(
        self,
        spec,  # Poetry version specifier (e.g., '^1.2.0', '~1.2.0', '1.*').
    ):
        """
            Convert Poetry-style version specifier to PEP 440 format.

            Args:
                spec: Poetry version specifier (e.g., '^1.2.0', '~1.2.0', '1.*').
            Returns:
                str: PEP 440 compatible version specifier.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        spec = spec.strip()
        
        # Handle space-separated multiple conditions like ">=3.14 <3.15"
        # Convert to comma-separated format ">=3.14,<3.15"
        if ' ' in spec and any(op in spec for op in ['==', '!=', '>=', '<=', '>', '<']):
            # Split on spaces and filter out empty strings
            parts = [p.strip() for p in spec.split() if p.strip()]
            # Join with commas
            spec = ','.join(parts)
        
        if spec.startswith("^"):
            base = pkg_version.parse(spec[1:])
            upper = f"{base.major + 1}.0"
            return f">={base},<{upper}"
        if spec.startswith("~"):
            base = pkg_version.parse(spec[1:])
            # If only major version specified (e.g., "~2"), match entire major version
            # by incrementing major version for upper bound (e.g., ">=2,<3")
            # If major.minor specified (e.g., "~2.3"), match by incrementing minor (e.g., ">=2.3,<2.4")
            version_parts = spec[1:].split('.')
            if len(version_parts) == 1:
                # Only major version, like "~2" -> ">=2,<3"
                upper = f"{base.major + 1}.0"
            else:
                # Has minor version, like "~2.3" -> ">=2.3,<2.4"
                upper = f"{base.major}.{base.minor + 1}"
            return f">={base},<{upper}"
        if spec.endswith(".*"):
            major = int(spec.split(".")[0])
            return f">={major},<{major + 1}"
        return spec

    def build_spec(
        self,
        v,  # Exact version string (e.g., '1.2.0').
        vmin,  # Minimum version string.
        vmax,  # Maximum version string.
        specifier,  # Poetry or PEP 440 version specifier.
    ):
        """
            Build a version specifier string from version constraints.

            Args:
                v: Exact version string (e.g., '1.2.0').
                vmin: Minimum version string.
                vmax: Maximum version string.
                specifier: Poetry or PEP 440 version specifier.
            Returns:
                str or None: Combined version specifier, or None if no constraints provided.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        parts = []
        if v: parts.append(f"=={v}")
        if vmin: parts.append(f">={vmin}")
        if vmax: parts.append(f"<={vmax}")
        if specifier: parts.append(self.poetry_to_pep440(specifier))
        return ",".join(parts) if parts else None

    def build_pip_requirement(
        self,
        name,  # Name identifier.
        version,  # Version string.
        vmin,  # Minimum allowed version string.
        vmax,  # Maximum allowed version string.
        specifier,  # Version specifier string.
    ):
        """
            Build a pip-compatible requirement string like 'numpy>=1.20,<2.0'

            Args:
                name: Name identifier.
                version: Version string.
                vmin: Minimum allowed version string.
                vmax: Maximum allowed version string.
                specifier: Version specifier string.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        spec = self.build_spec(version, vmin, vmax, specifier)
        if spec:
            return f"{name}{spec}"
        return name

    # ------------------------------------------------------------------
    # Subprocess KILL UTILITIES (Windows / Linux / macOS)
    # ------------------------------------------------------------------
    def kill_process_tree(
        self,
        pid,  # Process ID to kill.
    ):
        """
            Kill a process tree (process and all its children).

            Args:
                pid: Process ID to kill.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        try:
            # Linux / macOS
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            else:
                # Windows fallback
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Sync Installation with per-call timeout override
    # ------------------------------------------------------------------
    def pip_install_sync(
        self,
        pkg,  # Package requirement string (e.g., 'numpy>=1.20').
        silent,  # If True, suppress installation output.
        install_args,  # Additional pip install arguments string.
        timeout,  # Timeout in seconds (None for no timeout).
        con,  # If True, print console messages.
    ):
        """
            Install a Python package using pip synchronously.

            Args:
                pkg: Package requirement string (e.g., 'numpy>=1.20').
                silent: If True, suppress installation output.
                install_args: Additional pip install arguments string.
                timeout: Timeout in seconds (None for no timeout).
                con: If True, print console messages.
            Raises:
                RuntimeError: If installation is disabled, times out, or fails.

            Returns:
                dict: Operation result.
        """
        if not self.allow_install:
            raise RuntimeError(f"Installation disabled. Cannot install '{pkg}'.")

        timeout = timeout if timeout is not None else self.default_timeout

        x = f"Installing package '{pkg}' (sync; timeout={timeout})"
        if con:
            print ('')
            print (x)
        self.log("info", x)

        cmd = [sys.executable, "-m", "pip", "install", pkg]
        if install_args:
            cmd.extend(install_args.split())

        if con:
            print (f"  {' '.join(cmd)}") 

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=(subprocess.PIPE if not silent else subprocess.DEVNULL),
                stderr=(subprocess.PIPE if not silent else subprocess.DEVNULL),
                text=True,
                start_new_session=True,  # so killpg works on *nix
            )

            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.log("error", f"Timeout installing '{pkg}' after {timeout} seconds.")
                self.kill_process_tree(proc.pid)
                stdout, stderr = proc.communicate()

                raise RuntimeError(
                    f"Timeout installing '{pkg}' after {timeout} seconds:\n\n" +
                    self._output(stdout, stderr)
                )

            if proc.returncode != 0:
                raise RuntimeError(
                    f"pip install failed for '{pkg}':\n\n" +
                    self._output(stdout, stderr)
                )

        except Exception as e:
            raise

    def _output(
        self,
        stdout,  # Standard output string.
        stderr,  # Standard error string.
    ):
        """
            Combine stdout and stderr into a single output string.

            Args:
                stdout: Standard output string.
                stderr: Standard error string.
            Returns:
                str: Combined output with newline separator if both present.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        x = ''

        stdout = '' if stdout is None else stdout.strip()
        stderr = '' if stderr is None else stderr.strip()

        if stdout != '': x += stdout
        if stderr != '':
            if x != '': x += '\n'
            x += stderr

        return x
        

    # ------------------------------------------------------------------
    # ASYNC Installation with timeout + logging + full process kill
    # ------------------------------------------------------------------
    async def pip_install_async(
        self,
        pkg,  # Package requirement name or specifier.
        silent,  # If True, suppress installer output.
        install_args,  # Additional arguments passed to package installer.
        timeout,  # Timeout value in seconds.
        con,  # If True, print output to console.
    ):
        """
            Install a Python package asynchronously using pip with timeout support.

            Args:
                pkg: Package requirement name or specifier.
                silent: If True, suppress installer output.
                install_args: Additional arguments passed to package installer.
                timeout: Timeout value in seconds.
                con: If True, print output to console.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        try:
            import asyncio
        except ImportError:
            raise RuntimeError("asyncio not available")

        timeout = timeout if timeout is not None else self.default_timeout

        x = f"Installing package '{pkg}' (async; timeout={timeout})"
        if con:
            print ('')
            print (x)
        self.log("info", x)

        cmd = [sys.executable, "-m", "pip", "install", pkg]
        if install_args:
            cmd.extend(install_args.split())

        if con:
            print (f"  {' '.join(cmd)}") 

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=(asyncio.subprocess.PIPE if not silent else asyncio.subprocess.DEVNULL),
            stderr=(asyncio.subprocess.PIPE if not silent else asyncio.subprocess.DEVNULL),
            start_new_session=True,  # needed for killpg
        )

        try:
            if timeout is None:
                await proc.wait()
            else:
                await asyncio.wait_for(proc.wait(), timeout=timeout)

        except asyncio.TimeoutError:
            self.log("error", f"Timeout installing '{pkg}' asynchronously.")

            # Kill full process tree
            self.kill_process_tree(proc.pid)
            stdout, stderr = await proc.communicate()

            raise RuntimeError(
                f"Async install timeout for '{pkg}' after {timeout} seconds:\n\n" +
                self._output(stdout.decode(), stderr.decode())
            )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"Async pip install failed for '{pkg}':\n\n" +
                self._output(stdout.decode(), stderr.decode())
            )

    # ------------------------------------------------------------------
    # IMPORT Helpers
    # ------------------------------------------------------------------
    def try_import(
        self,
        name,  # Module name to import.
    ):
        """
            Try to import a Python module by name.

            Args:
                name: Module name to import.
            Returns:
                module or None: Module object if import succeeds, None if not found.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            return None

    # ------------------------------------------------------------------
    # Build cache key
    # ------------------------------------------------------------------
    def build_cache_key(
        self,
        name,  # Package name.
        version,  # Exact version string.
        vmin,  # Minimum version string.
        vmax,  # Maximum version string.
        specifier,  # Version specifier string.
        async_flag,  # True if async import, False otherwise.
    ):
        """
            Build a cache key for package lookup.

            Args:
                name: Package name.
                version: Exact version string.
                vmin: Minimum version string.
                vmax: Maximum version string.
                specifier: Version specifier string.
                async_flag: True if async import, False otherwise.
            Returns:
                str: Cache key string.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        return f"{name}|{version}|{vmin}|{vmax}|{specifier}|async={async_flag}"


    # ------------------------------------------------------------------
    # PUBLIC SYNC GET
    # ------------------------------------------------------------------
    def get(
        self,
        name,  # Package name to import.
        version = None,  # Exact version required.
        version_min = None,  # Minimum version required.
        version_max = None,  # Maximum version required.
        specifier = None,  # Version specifier (Poetry or PEP 440 format).
        *,
        silent = False,  # If True, suppress installation output.
        install_args = '',  # Additional pip install arguments.
        timeout = None,  # Installation timeout in seconds (overrides default).
        use_cache = True,  # If True, use cached results.
        allow_install = None,  # If True, allow package installation (overrides instance setting).
        con = False,  # If True, print console messages.
    ):
        """
            Get or install a Python package synchronously.

            Args:
                name: Package name to import.
                version: Exact version required.
                version_min: Minimum version required.
                version_max: Maximum version required.
                specifier: Version specifier (Poetry or PEP 440 format).
                silent: If True, suppress installation output.
                install_args: Additional pip install arguments.
                timeout: Installation timeout in seconds (overrides default).
                use_cache: If True, use cached results.
                allow_install: If True, allow package installation (overrides instance setting).
                con: If True, print console messages.
            Returns:
                PackageResult: Object with module, name, version, satisfies, specifier, and installed_now fields.

            Raises:
                Exception: Propagated runtime errors, if any.
        """

        if allow_install is None:
            allow_install = self.allow_install

        try:
            key = self.build_cache_key(name, version, version_min, version_max, specifier, False)

            if use_cache:
                with self.cache_lock:
                    if key in self.cache:
                        ### RETURN #############################################################
                        return {"return": 0, "package": self.cache[key]}

            module = self.try_import(name)
            installed_now = False

            if module is None:
                if not allow_install:
                    raise RuntimeError(f"Package '{name}' missing; installation disabled.")

                # Build requirement string with version constraints
                requirement = self.build_pip_requirement(name, version, version_min, version_max, specifier)
                self.pip_install_sync(requirement, silent, install_args, timeout, con)
                module = self.try_import(name)
                if module is None:
                    raise RuntimeError(f"Installed '{name}' but cannot import it.")
                installed_now = True

            pkg_ver = self.get_version(module)
            if pkg_ver is None:
                raise RuntimeError(f"Cannot determine version of '{name}'.")

            full_spec = self.build_spec(version, version_min, version_max, specifier)
            if full_spec:
                pv = pkg_version.parse(pkg_ver)
                if pv not in SpecifierSet(full_spec):
                    raise RuntimeError(
                        f"{name} version {pkg_ver} does NOT satisfy '{full_spec}'."
                    )

            result = PackageResult(module, name, pkg_ver, True, full_spec, installed_now)

            if use_cache:
                with self.cache_lock:
                    self.cache[key] = result

#            deps_name = 'python-' + name
#            dep = self.deps.setdefault(deps_name, {})
#            dep['package'] = result

            ### RETURN #############################################################

            return {"return": 0, "package": result}

        except Exception as e:
            self.log("error", f"[sync] {e} in {__name__}")
            if self.fail_on_error:
                raise
            return {"return": 1, "error": f'pip install failed for {name}: {e}'}

    # ------------------------------------------------------------------
    # PUBLIC ASYNC GET
    # ------------------------------------------------------------------
    async def get_async(
        self,
        name,  # Name identifier.
        version = None,  # Version string.
        version_min = None,  # Minimum allowed version string.
        version_max = None,  # Maximum allowed version string.
        specifier = None,  # Version specifier string.
        *,
        silent = False,  # If True, suppress installer output.
        install_args = '',  # Additional arguments passed to package installer.
        timeout = None,  # Timeout value in seconds.
        use_cache = True,  # If True, reuse cached values when available.
        allow_install = None,  # If True, allow automatic package installation.
        con = False,  # If True, print output to console.
    ):
        """
            Asynchronously resolve, optionally install, and validate a Python package.

            Args:
                name: Name identifier.
                version: Version string.
                version_min: Minimum allowed version string.
                version_max: Maximum allowed version string.
                specifier: Version specifier string.
                silent: If True, suppress installer output.
                install_args: Additional arguments passed to package installer.
                timeout: Timeout value in seconds.
                use_cache: If True, reuse cached values when available.
                allow_install: If True, allow automatic package installation.
                con: If True, print output to console.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """
        try:
            import asyncio
        except ImportError:
            return {"return": 1, "error": "asyncio not available"}

        if allow_install is None:
            allow_install = self.allow_install

        try:
            key = self.build_cache_key(name, version, version_min, version_max, specifier, True)

            if use_cache:
                with self.cache_lock:
                    if key in self.cache:
                        ### RETURN #############################################################
                        return {"return": 0, "package": self.cache[key]}

            module = await asyncio.to_thread(self.try_import, name)
            installed_now = False

            if module is None:
                if not allow_install:
                    raise RuntimeError(f"Package '{name}' missing; installation disabled.")

                # Build requirement string with version constraints
                requirement = self.build_pip_requirement(name, version, version_min, version_max, specifier)
                await self.pip_install_async(requirement, silent, install_args, timeout, con)
                module = await asyncio.to_thread(self.try_import, name)
                if module is None:
                    raise RuntimeError(f"Installed '{name}' but cannot import it.")
                installed_now = True

            pkg_ver = await asyncio.to_thread(self.get_version, module)
            if pkg_ver is None:
                raise RuntimeError(f"Cannot determine version of '{name}'.")

            full_spec = self.build_spec(version, version_min, version_max, specifier)
            if full_spec:
                pv = pkg_version.parse(pkg_ver)
                if pv not in SpecifierSet(full_spec):
                    raise RuntimeError(
                        f"{name} version {pkg_ver} does NOT satisfy '{full_spec}'."
                    )

            result = PackageResult(module, name, pkg_ver, True, full_spec, installed_now)

            if use_cache:
                with self.cache_lock:
                    self.cache[key] = result

#            deps_name = 'python-' + name
#            dep = self.deps.setdefault(deps_name, {})
#            dep['package'] = result

            ### RETURN #############################################################
            return {"return": 0, "package": result}

        except Exception as e:
            self.log("error", f"[async] {e} in {__name__}")
            if self.fail_on_error:
                raise
            return {"return": 1, "error": f'internal error "{e}" in {__name__}'}

    # ------------------------------------------------------------------
    # PUBLIC SYNC GET ALL
    # ------------------------------------------------------------------

    def get_all(
        self,
        pip_packages,  # Mapping of package names to resolution settings.
        con = False,  # If True, print output to console.
    ):
        """
            Resolve a mapping of packages synchronously and return module handles.

            Args:
                pip_packages: Mapping of package names to resolution settings.
                con: If True, print output to console.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        pkg = {}
        mpkg = {}

        for pip_package in pip_packages:
            pip_package_params = pip_packages[pip_package]
            if not pip_package_params: 
                pip_package_params = {}
            if self.add_install_args:
                x = pip_package_params.get('install_args')
                x = '' if not x else x + ' '
                pip_package_params['install_args'] = x + self.add_install_args

            r = self.get(pip_package, con = con, **pip_package_params)
            if r['return']>0: return r

            pkg[pip_package] = r['package']
            mpkg[pip_package] = r['package'].module

        return {'return':0, 'pkg': pkg, 'mpkg': mpkg}

    # ------------------------------------------------------------------
    # PUBLIC ASYNC GET ALL
    # ------------------------------------------------------------------

    async def get_async_all(
        self,
        pip_packages,  # Mapping of package names to resolution settings.
        con = False,  # If True, print output to console.
    ):
        """
            Resolve a mapping of packages asynchronously and return module handles.

            Args:
                pip_packages: Mapping of package names to resolution settings.
                con: If True, print output to console.
            Returns:
                dict: Operation result.
            Raises:
                Exception: Propagated runtime errors, if any.
        """

        pkg = {}
        mpkg = {}

        for pip_package in pip_packages:
            pip_package_params = pip_packages[pip_package]
            if not pip_package_params: 
                pip_package_params = {}
            if self.add_install_args:
                x = pip_package_params.get('install_args')
                x = '' if not x else x + ' '
                pip_package_params['install_args'] = x + self.add_install_args

            r = await self.get_async(pip_package, con = con, **pip_package_params)
            if r['return']>0: return r

            pkg[pip_package] = r['package']
            mpkg[pip_package] = r['package'].module

        return {'return':0, 'pkg': pkg, 'mpkg': mpkg}

    # ------------------------------------------------------------------
    # VERSION MATCHING
    # ------------------------------------------------------------------
    
    def normalize_detected_version(
        self,
        version_str,  # Version string that may contain platform identifiers,
    ):
        """
            Normalize non-standard version strings to PEP 440 compatible format.

            Args:
                version_str: Version string that may contain platform identifiers,
            Returns:
                str: Normalized version string compatible with packaging library.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        import re
        
        version_str = version_str.strip()
        
        # Handle platform identifiers like ".windows.", ".linux.", ".darwin.", etc.
        # Convert them to local version identifiers with '+'
        # e.g., "2.49.0.windows.1" -> "2.49.0+windows.1"
        #      "2.49.0.windows" -> "2.49.0+windows"
        # First, handle with trailing digits
        platform_pattern = r'\.(windows|linux|darwin|macos|win|mac|unix)\.(\d+)'
        if re.search(platform_pattern, version_str, re.IGNORECASE):
            version_str = re.sub(platform_pattern, r'+\1.\2', version_str, flags=re.IGNORECASE)
        else:
            # Handle platform identifiers at the end without trailing digits
            platform_pattern_end = r'\.(windows|linux|darwin|macos|win|mac|unix)$'
            if re.search(platform_pattern_end, version_str, re.IGNORECASE):
                version_str = re.sub(platform_pattern_end, r'+\1', version_str, flags=re.IGNORECASE)
        
        # Handle versions with dashes before text (like "2.49-win-3")
        # Convert to local version identifier: "2.49-win-3" -> "2.49+win.3"
        # But preserve standard pre-release identifiers (alpha, beta, rc, a, b, etc.)
        if '-' in version_str:
            # Check if it's a standard pre-release format (e.g., "1.0.0-alpha1", "2.0-rc1")
            prerelease_pattern = r'-?(alpha|beta|rc|a|b|c|pre|preview)(\d+)?'
            if not re.search(prerelease_pattern, version_str, re.IGNORECASE):
                # Not a standard pre-release, treat as local version
                # Split on first dash that's followed by non-numeric
                match = re.match(r'^([\d\.]+)[-_](.+)$', version_str)
                if match:
                    base_version = match.group(1)
                    local_part = match.group(2).replace('-', '.').replace('_', '.')
                    version_str = f"{base_version}+{local_part}"
        
        # Handle underscores in version numbers (e.g., "3.12_5" -> "3.12.5")
        # But only in the numeric part
        if '_' in version_str and '+' not in version_str:
            # Replace underscores with dots in the main version part
            version_str = version_str.replace('_', '.')
        
        return version_str
    
    def match_version(
        self,
        requested_version,  # Version requirement in Poetry or PyPI format
        detected_version,  # Installed version string (e.g., '2.3.1', '2.3.windows.1',
    ):
        """
            Check if a detected version matches a requested version specifier.

            Args:
                requested_version: Version requirement in Poetry or PyPI format
                detected_version: Installed version string (e.g., '2.3.1', '2.3.windows.1',
            Returns:
                dict: {'return': 0, 'matched': bool} on success,
                      {'return': 1, 'error': str} on error.

            Raises:
                Exception: Propagated runtime errors, if any.
        """
        if not requested_version or not detected_version:
            return {'return':0, 'matched': False}
        
        try:
            requested = requested_version.strip()
            detected = detected_version.strip()
            
            # Check if requested version has no operator
            has_operator = any(op in requested for op in ['==', '!=', '>=', '<=', '>', '<', '^', '~', '*'])
            
            # Check if requested version has platform identifiers (local versions)
            # We'll use this later to determine if we should strip local versions from detected
            requested_has_local = False
            
            # Quick check: if no operator and strings match exactly, return immediately
            if not has_operator and requested == detected:
                return {'return':0, 'matched': True}
            
            # Normalize and parse detected version
            detected_clean = self.normalize_detected_version(detected)
            
            # Try to parse the detected version
            try:
                detected_parsed = pkg_version.parse(detected_clean)
            except Exception as e:
                err = f"Error parsing detected version: {e}"
                return {'return':1, 'error':err}
            
            # Handle requested version
            if not has_operator:
                # Plain version number - normalize it too (handles platform identifiers)
                requested_clean = self.normalize_detected_version(requested)
                
                # Try to parse the normalized requested version
                try:
                    requested_parsed = pkg_version.parse(requested_clean)
                    
                    # Track if requested has local versions
                    if requested_parsed.local:
                        requested_has_local = True
                    
                    # Check for exact match after normalization
                    if requested_parsed == detected_parsed:
                        return {'return':0, 'matched': True}
                    
                    # If both have local versions (platform identifiers), check platform match
                    if requested_parsed.local and detected_parsed.local:
                        # Extract platform name (first part before any dot in local)
                        req_platform = requested_parsed.local.split('.')[0]
                        det_platform = detected_parsed.local.split('.')[0]
                        
                        # If platforms don't match, fail immediately
                        if req_platform != det_platform:
                            return {'return':0, 'matched': False}
                        
                        # Platforms match, do prefix matching
                        if (requested_parsed.public == detected_parsed.public and
                            detected_parsed.local.startswith(requested_parsed.local)):
                            return {'return':0, 'matched': True}
                    
                    # For versions with local identifiers, we can't use them in specifiers
                    # Strip the local part and use base version for near match
                    # e.g., "2.49.0+windows" -> use "~2.49.0" to match "2.49.0+windows.1"
                    if requested_parsed.local:
                        # Use the public (base) version for specifier matching
                        requested = f"~{requested_parsed.public}"
                    else:
                        # No local version, safe to use as-is
                        requested = f"~{requested_clean}"
                except:
                    # If parsing fails, try treating as near match with original value
                    requested = f"~{requested}"
            else:
                # Has operator - need to handle operators with platform identifiers
                import re
                
                # First, extract and check platform identifiers from the requested version
                # Pattern to match operator + version
                pattern = r'(==|!=|>=|<=|>|<|\^|~)([^\s,]+)'
                matches = re.findall(pattern, requested)
                
                # Check if any version part has a platform identifier that conflicts
                # Also track if requested has any local versions
                for operator, version_part in matches:
                    # Normalize the requested version part
                    normalized = self.normalize_detected_version(version_part)
                    try:
                        parsed = pkg_version.parse(normalized)
                        
                        # Track if requested has local versions
                        if parsed.local:
                            requested_has_local = True
                        
                        # If both have platform identifiers, they must match
                        if parsed.local and detected_parsed.local:
                            # Extract platform name (first part before any dot in local)
                            req_platform = parsed.local.split('.')[0]
                            det_platform = detected_parsed.local.split('.')[0]
                            
                            # If platforms don't match, fail immediately
                            if req_platform != det_platform:
                                return {'return':0, 'matched': False}
                    except:
                        pass  # Continue if parsing fails
                
                # Special handling for == and != with platform identifiers
                # These should do exact/prefix matching on the full version including local parts
                if requested.startswith('==') or requested.startswith('!='):
                    # Extract the version part after the operator
                    operator = requested[:2]
                    version_part = requested[2:].strip()
                    
                    # Normalize the requested version
                    requested_clean = self.normalize_detected_version(version_part)
                    try:
                        requested_parsed = pkg_version.parse(requested_clean)
                        
                        if operator == '==':
                            # Check for exact match
                            if requested_parsed == detected_parsed:
                                return {'return':0, 'matched': True}
                            
                            # If both have local versions, do prefix matching
                            if requested_parsed.local and detected_parsed.local:
                                if (requested_parsed.public == detected_parsed.public and
                                    detected_parsed.local.startswith(requested_parsed.local)):
                                    return {'return':0, 'matched': True}
                            
                            return {'return':0, 'matched': False}
                        else:  # !=
                            # Check for non-equality
                            if requested_parsed == detected_parsed:
                                return {'return':0, 'matched': False}
                            
                            # If both have local versions, check prefix
                            if requested_parsed.local and detected_parsed.local:
                                if (requested_parsed.public == detected_parsed.public and
                                    detected_parsed.local.startswith(requested_parsed.local)):
                                    return {'return':0, 'matched': False}
                            
                            return {'return':0, 'matched': True}
                    except Exception as e:
                        err = f"Error parsing requested version in == or !=: {e}"
                        return {'return':1, 'error':err}
                
                # For inequality operators (>=, <=, >, <) with local versions,
                # we need to do manual comparison because SpecifierSet doesn't support local versions
                # Check if we need manual comparison
                inequality_pattern = r'(>=|<=|>|<)([^\s,]+)'
                inequality_matches = re.findall(inequality_pattern, requested)
                
                needs_manual_comparison = False
                for op, ver_part in inequality_matches:
                    normalized = self.normalize_detected_version(ver_part)
                    try:
                        parsed = pkg_version.parse(normalized)
                        if parsed.local and detected_parsed.local:
                            needs_manual_comparison = True
                            break
                    except:
                        pass
                
                # If manual comparison is needed for inequality operators with local versions
                if needs_manual_comparison:
                    # Parse and evaluate each condition manually
                    # Handle space-separated conditions like ">=2.49.0.windows.2 <2.50"
                    conditions = requested.replace(',', ' ').split()
                    
                    for condition in conditions:
                        condition = condition.strip()
                        if not condition:
                            continue
                        
                        # Extract operator and version
                        match = re.match(r'^(==|!=|>=|<=|>|<|\^|~)(.+)$', condition)
                        if not match:
                            continue
                        
                        op = match.group(1)
                        ver_part = match.group(2)
                        
                        # Normalize and parse
                        normalized = self.normalize_detected_version(ver_part)
                        try:
                            cond_parsed = pkg_version.parse(normalized)
                        except:
                            continue
                        
                        # Perform comparison based on operator
                        if op == '>=':
                            if not (detected_parsed >= cond_parsed):
                                return {'return':0, 'matched': False}
                        elif op == '<=':
                            if not (detected_parsed <= cond_parsed):
                                return {'return':0, 'matched': False}
                        elif op == '>':
                            if not (detected_parsed > cond_parsed):
                                return {'return':0, 'matched': False}
                        elif op == '<':
                            if not (detected_parsed < cond_parsed):
                                return {'return':0, 'matched': False}
                        elif op == '~':
                            # Near match - check if base version matches
                            if cond_parsed.public != detected_parsed.public:
                                return {'return':0, 'matched': False}
                        elif op == '^':
                            # Caret operator - convert to range and check
                            spec_str = self.poetry_to_pep440(f"^{cond_parsed.public}")
                            try:
                                spec_set = SpecifierSet(spec_str)
                                if not spec_set.contains(detected_parsed, prereleases=True):
                                    return {'return':0, 'matched': False}
                            except:
                                return {'return':0, 'matched': False}
                    
                    return {'return':0, 'matched': True}
                
                # For other operators (>=, <=, >, <, ^, ~), strip local versions for the specifier
                # Platform check was already done above
                def normalize_version_in_spec(
                    match,  # Value for match.
                ):
                    """
                        Normalize version tokens in specifiers to comparable public versions.

                        Args:
                            match: Value for match.
                        Returns:
                            dict: Operation result.
                        Raises:
                            Exception: Propagated runtime errors, if any.
                    """
                    operator = match.group(1)
                    version_part = match.group(2)
                    # Normalize and strip local version
                    normalized = self.normalize_detected_version(version_part)
                    try:
                        parsed = pkg_version.parse(normalized)
                        # Use public (base) version without local part
                        return f"{operator}{parsed.public}"
                    except:
                        # If parsing fails, return as-is
                        return match.group(0)
                
                # Pattern to match operator + version
                pattern = r'(>=|<=|>|<|\^|~)([^\s,]+)'
                requested = re.sub(pattern, normalize_version_in_spec, requested)
            
            # Convert Poetry format to PEP 440 if needed
            spec_string = self.poetry_to_pep440(requested)
            
            # Create specifier set and check if detected version matches
            spec_set = SpecifierSet(spec_string)
            
            # If requested version doesn't have platform identifiers but detected does,
            # use only the base (public) version for comparison
            if not requested_has_local and detected_parsed.local:
                # Use public version only (e.g., "2.49.0" instead of "2.49.0+windows.2")
                version_to_check = pkg_version.parse(str(detected_parsed.public))
            else:
                version_to_check = detected_parsed
            
            # Include pre-releases (alpha, beta, rc, etc.) in version matching
            # This allows "3.14" to match "3.14.0b2" or similar pre-release versions
            matched = spec_set.contains(version_to_check, prereleases=True)
            
            # Special handling for pre-releases: if detected is a pre-release and didn't match,
            # check if the base version (without pre-release tag) would match
            # This handles cases like "3.14" matching "3.14.0b2" where b2 < final 3.14.0
            if not matched and version_to_check.is_prerelease:
                # Check if the base release version (without pre-release tag) matches
                # For "3.14.0b2", the base is "3.14.0"
                base_version_str = f"{version_to_check.major}.{version_to_check.minor}.{version_to_check.micro}"
                base_version = pkg_version.parse(base_version_str)
                matched = spec_set.contains(base_version, prereleases=True)
            
            return {'return':0, 'matched': matched}
            
        except Exception as e:
            err = f"Error matching version '{requested_version}' with '{detected_version}': {e}"
            return {'return':1, 'error':err}
