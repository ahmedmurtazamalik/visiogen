"""Generate the redistributable A2 candidate-classification corpus."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

_SIZE = (640, 480)


def _arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
    draw.line((start, end), fill="black", width=5)
    draw.polygon(
        [(end[0], end[1]), (end[0] - 14, end[1] - 9), (end[0] - 14, end[1] + 9)],
        fill="black",
    )


def write_candidate_fixture(path: Path, kind: str) -> Path:
    """Write one deterministic synthetic classification fixture."""

    image = Image.new("RGB", _SIZE, "white")
    draw = ImageDraw.Draw(image)
    if kind == "linear_flow":
        for index, label in enumerate(("Input", "Process", "Output")):
            left = 40 + index * 205
            draw.rounded_rectangle(
                (left, 185, left + 145, 285),
                radius=12,
                outline="black",
                width=4,
            )
            draw.text((left + 40, 225), label, fill="black")
            if index < 2:
                _arrow(draw, (left + 145, 235), (left + 195, 235))
    elif kind == "system_architecture":
        draw.rectangle((45, 70, 595, 410), outline="navy", width=5)
        for box, label in [((90, 155, 235, 255), "Sensor"), ((405, 155, 550, 255), "Service")]:
            draw.rectangle(box, outline="black", width=4)
            draw.text((box[0] + 42, box[1] + 42), label, fill="black")
        _arrow(draw, (235, 205), (405, 205))
        draw.text((65, 90), "Edge System", fill="navy")
    elif kind == "component_schematic":
        draw.rectangle((95, 145, 245, 290), outline="black", width=4)
        draw.ellipse((405, 155, 535, 285), outline="black", width=4)
        draw.text((135, 200), "CPU 10", fill="black")
        draw.text((440, 210), "RF 20", fill="black")
        draw.line((245, 220, 405, 220), fill="black", width=5)
    elif kind == "photo_pattern":
        for y in range(_SIZE[1]):
            for x in range(_SIZE[0]):
                image.putpixel((x, y), ((x * 3 + y) % 256, (x + y * 2) % 256, (x + y) % 180))
    elif kind == "bar_chart":
        draw.line((80, 390, 570, 390), fill="black", width=4)
        draw.line((80, 70, 80, 390), fill="black", width=4)
        for index, height in enumerate((110, 230, 170, 290)):
            left = 125 + index * 105
            draw.rectangle((left, 390 - height, left + 65, 390), fill="steelblue")
    elif kind == "data_table":
        for x in (70, 235, 400, 565):
            draw.line((x, 90, x, 390), fill="black", width=3)
        for y in (90, 165, 240, 315, 390):
            draw.line((70, y, 565, y), fill="black", width=3)
        draw.text((95, 115), "Name", fill="black")
        draw.text((260, 115), "Value", fill="black")
    elif kind == "decorative_logo":
        draw.ellipse((145, 85, 495, 395), fill="darkorange", outline="maroon", width=10)
        draw.text((250, 220), "ACME", fill="white")
    elif kind == "blurred_mixed_content":
        draw.rectangle((120, 150, 270, 280), outline="gray", width=3)
        draw.ellipse((365, 150, 515, 280), outline="gray", width=3)
        draw.line((270, 215, 365, 215), fill="gray", width=3)
        image = image.resize((64, 48)).filter(ImageFilter.GaussianBlur(radius=5)).resize(_SIZE)
    else:
        raise ValueError(f"Unknown candidate fixture kind: {kind}")
    image.save(path, format="PNG", compress_level=9)
    return path
