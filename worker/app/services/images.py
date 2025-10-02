from functools import lru_cache
from worker.app.config import settings


@lru_cache(maxsize=1)
def _get_caption_pipeline():
    # Import lazily to keep worker startup fast
    from transformers import pipeline

    return pipeline("image-to-text", model=settings.IMAGES_CAPTION_MODEL)  # BLIP base


def generate_caption(image_path: str) -> str:
    if not settings.IMAGES_CAPTION:
        return ""
    try:
        pipe = _get_caption_pipeline()
        # Load and preprocess image manually to avoid pipeline issues
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        # Ensure minimum size for BLIP model
        if image.size[0] < 224 or image.size[1] < 224:
            image = image.resize((224, 224), Image.Resampling.LANCZOS)
        out = pipe(image)
        if isinstance(out, list) and out and "generated_text" in out[0]:
            return str(out[0]["generated_text"]).strip()
    except Exception as e:
        # log and soft-fallback
        print(f"[images] caption failed: {e}")
    return ""
