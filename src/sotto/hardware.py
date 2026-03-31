"""Hardware capability detection and model auto-selection."""

import logging
import sys
from dataclasses import dataclass

logger = logging.getLogger("sotto")


@dataclass
class HardwareProfile:
    cuda_available: bool
    vram_gb: float
    device_name: str


def detect_hardware() -> HardwareProfile:
    """Query CUDA availability and VRAM via CTranslate2 (the actual inference engine).

    Does NOT use torch.cuda — silero-vad pulls in CPU-only PyTorch, which
    always reports CUDA as unavailable even when the GPU works fine via CTranslate2.
    Falls back to torch only for VRAM/device name (not available via CTranslate2 API).
    """
    if sys.platform == "darwin":
        return HardwareProfile(cuda_available=False, vram_gb=0.0, device_name="CPU")

    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            # CTranslate2 confirms CUDA works — get VRAM and device name
            vram_gb = 0.0
            device_name = "CUDA GPU"

            # Try torch first (gives clean API for device properties)
            try:
                import torch
                if torch.cuda.is_available():
                    idx = torch.cuda.current_device()
                    props = torch.cuda.get_device_properties(idx)
                    vram_gb = props.total_memory / (1024 ** 3)
                    device_name = props.name
            except Exception:
                pass

            # If torch couldn't get VRAM (CPU-only build), fall back to nvidia-smi
            if vram_gb == 0.0:
                try:
                    import subprocess
                    result = subprocess.run(
                        ["nvidia-smi", "--query-gpu=memory.total,name", "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result.returncode == 0:
                        first_line = result.stdout.strip().splitlines()[0]
                        parts = first_line.split(",")
                        vram_gb = float(parts[0].strip()) / 1024  # MiB to GiB
                        device_name = parts[1].strip() if len(parts) > 1 else "CUDA GPU"
                except Exception as e:
                    logger.debug("nvidia-smi fallback failed: %s", e)

            return HardwareProfile(
                cuda_available=True,
                vram_gb=round(vram_gb, 1),
                device_name=device_name,
            )
    except Exception as e:
        logger.debug("CUDA detection failed: %s", e)
    return HardwareProfile(cuda_available=False, vram_gb=0.0, device_name="CPU")


# (min_vram_gb, model_name, human_label)
_TIERS: list[tuple[float, str, str]] = [
    (6.0, "large-v3-turbo", "high-VRAM GPU"),
    (3.0, "distil-large-v3", "mid-range GPU"),
    (1.0, "base", "low-VRAM GPU"),
]


def select_model(profile: HardwareProfile) -> tuple[str, str]:
    """Return (model_size, description) for the given hardware profile."""
    if profile.cuda_available:
        for min_vram, model, label in _TIERS:
            if profile.vram_gb >= min_vram:
                return model, (
                    f"GPU: {profile.device_name} ({profile.vram_gb:.0f} GB VRAM)\n"
                    f"Selected {model} ({label})"
                )
    return "base", "No CUDA GPU detected\nSelected base model (CPU mode)"
