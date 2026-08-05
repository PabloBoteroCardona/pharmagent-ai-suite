"""Genera imágenes JPEG sintéticas de recetas a partir de `PRESCRIPTION_DATASET`.

Renderiza texto plano sobre un fondo blanco con Pillow — no son fotografías ni escaneos
reales de recetas, son *ground truth* controlado para poder medir la tasa de extracción
correcta de `PrescriptionAgent` sin depender de imágenes reales (que implicarían datos de
salud de pacientes reales, fuera de alcance y de las garantías RGPD de este TFM).

Uso: python -m evaluation.generate_synthetic_prescriptions
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from evaluation.dataset import PRESCRIPTION_DATASET

OUTPUT_DIR = Path(__file__).parent / "synthetic_prescriptions"

IMAGE_SIZE = (800, 600)
BACKGROUND_COLOR = "white"
TEXT_COLOR = "black"
FONT_CANDIDATES = (
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)
FONT_SIZE = 28
LINE_SPACING = 20
MARGIN = 40


def _load_font() -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, FONT_SIZE)
    return ImageFont.load_default()


def render_prescription_image(case_id: str, lines: list[str]) -> Image.Image:
    """Renderiza `lines` como una imagen de receta sintética."""
    image = Image.new("RGB", IMAGE_SIZE, color=BACKGROUND_COLOR)
    draw = ImageDraw.Draw(image)
    font = _load_font()

    header = f"RECETA MEDICA (sintetica) - caso: {case_id}"
    draw.text((MARGIN, MARGIN), header, fill=TEXT_COLOR, font=font)

    y = MARGIN + FONT_SIZE + LINE_SPACING * 2
    for line in lines:
        draw.text((MARGIN, y), line, fill=TEXT_COLOR, font=font)
        y += FONT_SIZE + LINE_SPACING

    return image


def generate_all() -> list[Path]:
    """Genera y guarda todas las imágenes de `PRESCRIPTION_DATASET`. Devuelve las rutas."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    paths = []
    for case in PRESCRIPTION_DATASET:
        image = render_prescription_image(case.case_id, case.prescription_lines)
        path = OUTPUT_DIR / f"{case.case_id}.jpg"
        image.save(path, "JPEG", quality=95)
        paths.append(path)
    return paths


if __name__ == "__main__":
    generated = generate_all()
    print(f"{len(generated)} imágenes sintéticas generadas en {OUTPUT_DIR}:")
    for path in generated:
        print(f"  - {path.name}")
