"""Hardware capability detection and model auto-selection."""

import logging
from dataclasses import dataclass

logger = logging.getLogger("sotto")


@dataclass
class HardwareProfile:
    cuda_available: bool
    vram_gb: float
    device_name: str


def detect_hardware() -> HardwareProfile:
    """Query CUDA availability and VRAM. Safe to call if CUDA is absent."""
    try:
        import torch
        if torch.cuda.is_available():
            idx = torch.cuda.current_device()
            props = torch.cuda.get_device_properties(idx)
            vram_gb = props.total_memory / (1024 ** 3)
            return HardwareProfile(
                cuda_available=True,
                vram_gb=round(vram_gb, 1),
                device_name=props.name,
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
