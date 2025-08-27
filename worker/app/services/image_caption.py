from __future__ import annotations
from pathlib import Path
from app.config import settings

_BLIP = None


def _load():
    global _BLIP
    if _BLIP:
        return _BLIP
    try:
        from PIL import Image
        from transformers import BlipProcessor, BlipForConditionalGeneration

        proc = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        model = BlipForConditionalGeneration.from_pretrained(
            "Salesforce/blip-image-captioning-base"
        )
        _BLIP = (proc, model, Image)
        return _BLIP
    except Exception:
        if settings.EMBED_DEV_MODE:
            _BLIP = ("DEV", None, None)
            return _BLIP
        raise


def caption_image(path: str | Path) -> str:
    proc, _model, Image = _load()
    if proc == "DEV":
        return f"[DEV] caption for {Path(path).name}"
    inputs = proc(images=Image.open(path).convert("RGB"), return_tensors="pt")
    out = _model.generate(**inputs, max_length=32)
    return proc.decode(out[0], skip_special_tokens=True).strip()
