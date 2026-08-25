"""Generate the reviewed A3 semantic-reconstruction corpus."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


def _font(size: int = 28) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str) -> None:
    bounds = draw.textbbox((0, 0), text, font=_font())
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    x = (box[0] + box[2] - width) // 2
    y = (box[1] + box[3] - height) // 2
    draw.text((x, y), text, fill="black", font=_font())


def _box(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str) -> None:
    draw.rounded_rectangle(box, radius=14, fill="white", outline="black", width=5)
    _centered_text(draw, box, label)


def _arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    both: bool = False,
) -> None:
    draw.line((start, end), fill="black", width=6)
    draw.polygon(
        [(end[0], end[1]), (end[0] - 18, end[1] - 11), (end[0] - 18, end[1] + 11)],
        fill="black",
    )
    if both:
        draw.polygon(
            [
                (start[0], start[1]),
                (start[0] + 18, start[1] - 11),
                (start[0] + 18, start[1] + 11),
            ],
            fill="black",
        )


def write_semantic_fixture(path: Path, kind: str) -> Path:
    """Write one deterministic annotated diagram image."""

    size = (2400, 1400) if kind == "dense_tiled" else (1000, 700)
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    if kind == "branching_flow":
        boxes = {
            "Start": (60, 280, 240, 400),
            "Valid?": (350, 280, 550, 400),
            "Approve": (700, 100, 930, 220),
            "Reject": (700, 480, 930, 600),
        }
        for label, box in boxes.items():
            _box(draw, box, label)
        _arrow(draw, (240, 340), (350, 340))
        draw.line((550, 340, 620, 340, 620, 160, 700, 160), fill="black", width=6)
        _arrow(draw, (680, 160), (700, 160))
        draw.line((550, 340, 620, 340, 620, 540, 700, 540), fill="black", width=6)
        _arrow(draw, (680, 540), (700, 540))
        draw.text((625, 115), "Yes", fill="black", font=_font(24))
        draw.text((625, 550), "No", fill="black", font=_font(24))
    elif kind == "contained_system":
        draw.rounded_rectangle((300, 90, 930, 610), radius=20, outline="navy", width=7)
        draw.text((330, 110), "Platform", fill="navy", font=_font(30))
        boxes = {
            "Client": (40, 280, 240, 410),
            "Gateway": (370, 280, 590, 410),
            "Service": (680, 280, 880, 410),
        }
        for label, box in boxes.items():
            _box(draw, box, label)
        _arrow(draw, (240, 345), (370, 345))
        _arrow(draw, (590, 345), (680, 345))
    elif kind == "reference_schematic":
        boxes = {
            "Sensor 10": (40, 270, 270, 420),
            "Processor 20": (380, 270, 650, 420),
            "Memory 30": (760, 270, 970, 420),
        }
        for label, box in boxes.items():
            _box(draw, box, label)
        _arrow(draw, (270, 345), (380, 345))
        _arrow(draw, (650, 345), (760, 345), both=True)
    elif kind == "crossing_without_junction":
        boxes = {
            "A": (40, 90, 210, 210),
            "B": (790, 90, 960, 210),
            "C": (40, 490, 210, 610),
            "D": (790, 490, 960, 610),
        }
        for label, box in boxes.items():
            _box(draw, box, label)
        _arrow(draw, (210, 150), (790, 550))
        _arrow(draw, (210, 550), (790, 150))
        draw.ellipse((488, 338, 512, 362), fill="white")
        draw.arc((480, 330, 520, 370), 200, 340, fill="black", width=5)
    elif kind == "dense_tiled":
        positions = {
            "Node 1": (80, 180, 420, 350),
            "Node 2": (820, 180, 1160, 350),
            "Node 3": (1560, 180, 1900, 350),
            "Node 4": (80, 950, 420, 1120),
            "Node 5": (820, 950, 1160, 1120),
            "Node 6": (1560, 950, 1900, 1120),
        }
        for label, box in positions.items():
            _box(draw, box, label)
        for start, end in [
            ((420, 265), (820, 265)),
            ((1160, 265), (1560, 265)),
            ((420, 1035), (820, 1035)),
            ((1160, 1035), (1560, 1035)),
            ((990, 350), (990, 950)),
        ]:
            if start[0] == end[0]:
                draw.line((start, end), fill="black", width=7)
                draw.polygon(
                    [(end[0], end[1]), (end[0] - 12, end[1] - 20), (end[0] + 12, end[1] - 20)],
                    fill="black",
                )
            else:
                _arrow(draw, start, end)
    elif kind == "ambiguous_arrow":
        _box(draw, (70, 270, 300, 420), "Source")
        _box(draw, (700, 270, 930, 420), "Target")
        draw.line((300, 345, 700, 345), fill=(95, 95, 95), width=5)
        faint = Image.new("RGBA", image.size, (255, 255, 255, 0))
        faint_draw = ImageDraw.Draw(faint)
        faint_draw.polygon(((690, 345), (662, 327), (662, 363)), fill=(120, 120, 120, 70))
        faint = faint.filter(ImageFilter.GaussianBlur(radius=8))
        image = Image.alpha_composite(image.convert("RGBA"), faint).convert("RGB")
    else:
        raise ValueError(f"Unknown semantic fixture kind: {kind}")
    image.save(path, format="PNG", compress_level=9)
    return path
