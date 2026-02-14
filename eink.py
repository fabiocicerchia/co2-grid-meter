
from PIL import Image, ImageDraw
from config import Config

def update_eink(ci, verdict):
    img = Image.new("1", (400, 300), 1)
    d = ImageDraw.Draw(img)
    d.text((10,10), f"CO2: {ci}", fill=0)
    d.text((10,40), f"{verdict}", fill=0)
    img.save(Config.EINK_PREVIEW_PATH)
