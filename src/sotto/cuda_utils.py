"""CUDA DLL path setup for Windows.

CTranslate2 needs cublas64_12.dll for CUDA. The nvidia-cublas-cu12 pip
package installs it under site-packages/nvidia/cublas/bin/ which isn't
on PATH by default. Call ensure_cuda_dlls() before any CUDA imports.
"""

import os


def ensure_cuda_dlls() -> None:
    """Add nvidia-cublas-cu12 DLL directory to PATH and DLL search list."""
    try:
        import importlib.util
        spec = importlib.util.find_spec("nvidia.cublas")
        if spec and spec.submodule_search_locations:
            bin_dir = os.path.join(list(spec.submodule_search_locations)[0], "bin")
            if os.path.isdir(bin_dir):
                os.add_dll_directory(bin_dir)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass
