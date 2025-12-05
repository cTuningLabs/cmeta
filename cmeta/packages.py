"""
Package Manager class

cMeta author and developer: (C) 2025 Grigori Fursin

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
    specifier: str | None
    installed_now: bool


class Packages:
    def __init__(
        self,
        cfg=None,
        cache=None,
        logger=None,
        fail_on_error=False,
        allow_install=True,
        timeout: float | None = None,   # global default timeout
    ):

        self.cache = cache or {}
        self.cfg = cfg or {}
        self.cache_lock = threading.Lock()
        self.logger = logger
        self.fail_on_error = fail_on_error
        self.allow_install = allow_install
        self.default_timeout = timeout  # seconds or None

    # ------------------------------------------------------------------
    # Logging wrapper
    # ------------------------------------------------------------------
    def log(self, level, msg):
        if self.logger:
            fn = getattr(self.logger, level, None)
            if callable(fn):
                fn(msg)

    # ------------------------------------------------------------------
    # Version helpers
    # ------------------------------------------------------------------
    def get_version(self, module):
        if hasattr(module, "__version__"):
            return module.__version__
        try:
            from importlib.metadata import version
            return version(module.__name__)
        except Exception:
            return None

    def poetry_to_pep440(self, spec):
        spec = spec.strip()
        if spec.startswith("^"):
            base = pkg_version.parse(spec[1:])
            upper = f"{base.major + 1}.0"
            return f">={base},<{upper}"
        if spec.startswith("~"):
            base = pkg_version.parse(spec[1:])
            upper = f"{base.major}.{base.minor + 1}"
            return f">={base},<{upper}"
        if spec.endswith(".*"):
            major = int(spec.split(".")[0])
            return f">={major},<{major + 1}"
        return spec

    def build_spec(self, v, vmin, vmax, specifier):
        parts = []
        if v: parts.append(f"=={v}")
        if vmin: parts.append(f">={vmin}")
        if vmax: parts.append(f"<={vmax}")
        if specifier: parts.append(self.poetry_to_pep440(specifier))
        return ",".join(parts) if parts else None

    def build_pip_requirement(self, name, version, vmin, vmax, specifier):
        """Build a pip-compatible requirement string like 'numpy>=1.20,<2.0'"""
        spec = self.build_spec(version, vmin, vmax, specifier)
        if spec:
            return f"{name}{spec}"
        return name

    # ------------------------------------------------------------------
    # Subprocess KILL UTILITIES (Windows / Linux / macOS)
    # ------------------------------------------------------------------
    def kill_process_tree(self, pid):
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
    def pip_install_sync(self, pkg, silent, install_args, timeout, con):
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
            print (f'  {' '.join(cmd)}') 

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

    def _output(self, stdout, stderr):
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
    async def pip_install_async(self, pkg, silent, install_args, timeout, con):
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
            print (f'  {' '.join(cmd)}') 

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
    def try_import(self, name):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            return None

    # ------------------------------------------------------------------
    # Build cache key
    # ------------------------------------------------------------------
    def build_cache_key(self, name, version, vmin, vmax, specifier, async_flag):
        return f"{name}|{version}|{vmin}|{vmax}|{specifier}|async={async_flag}"

    # ------------------------------------------------------------------
    # PUBLIC SYNC GET
    # ------------------------------------------------------------------
    def get(
        self,
        name,
        version=None,
        version_min=None,
        version_max=None,
        specifier=None,
        *,
        silent=False,
        install_args="",
        timeout=None,            # per-call override
        use_cache=True,
        allow_install=None,
        con=False,
    ):

        if allow_install is None:
            allow_install = self.allow_install

        try:
            key = self.build_cache_key(name, version, version_min, version_max, specifier, False)

            if use_cache:
                with self.cache_lock:
                    if key in self.cache:
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

            return {"return": 0, "package": result}

        except Exception as e:
            self.log("error", f"[sync] {e}")
            if self.fail_on_error:
                raise
            return {"return": 1, "error": str(e)}

    # ------------------------------------------------------------------
    # PUBLIC ASYNC GET
    # ------------------------------------------------------------------
    async def get_async(
        self,
        name,
        version=None,
        version_min=None,
        version_max=None,
        specifier=None,
        *,
        silent=False,
        install_args="",
        timeout=None,       # per-call override
        use_cache=True,
        allow_install=None,
        con=False,
    ):
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

            return {"return": 0, "package": result}

        except Exception as e:
            self.log("error", f"[async] {e}")
            if self.fail_on_error:
                raise
            return {"return": 1, "error": str(e)}
