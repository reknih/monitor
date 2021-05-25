from datetime import datetime
from dateutil.relativedelta import relativedelta
from math import ceil
from random import random
from time import sleep
import sys
import locale
import logging

from astral.sun import sun
from PIL import Image, ImageDraw, ImageTk, ImageFont
import pytz

import departures
import wetter

DEBUG = "--debug" in sys.argv
REFRESH = 5

if DEBUG:
    import tkinter as tk
else:
    from waveshare_epd import epd7in5_HD

locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')

class App:
    WIDTH, HEIGHT = (880,528)
    def __init__(self):
        logging.info("Starting")

        self.font_paths = {
            "regular": "fonts/OpenSans-Regular.ttf",
            "bold": "fonts/OpenSans-Bold.ttf",
            "italic": "fonts/OpenSans-Italic.ttf",
            "semibold": "fonts/OpenSans-SemiBold.ttf",
            "semibold-italic": "fonts/OpenSans-SemiBoldItalic.ttf",
            "condensed": "fonts/OpenSans-CondensedRegular.ttf",
            "condensed-bold": "fonts/OpenSans-CondensedBold.ttf",
            "condensed-bold-italic": "fonts/OpenSans-CondensedBoldItalic.ttf",
        }

        self.fonts = {
            "small-line": ImageFont.truetype(self.font_paths["condensed-bold"], 22),
            "large-line": ImageFont.truetype(self.font_paths["condensed-bold"], 26),
            "large-destination": ImageFont.truetype(self.font_paths["semibold"], 32),
            "small-destination": ImageFont.truetype(self.font_paths["regular"], 27),
            "large-arrival": ImageFont.truetype(self.font_paths["regular"], 32),
            "small-arrival": ImageFont.truetype(self.font_paths["italic"], 27),
            "claim": ImageFont.truetype(self.font_paths["semibold-italic"], 17),
            "clock": ImageFont.truetype(self.font_paths["bold"], 71),
            "date": ImageFont.truetype(self.font_paths["italic"], 25),
            "temperature": ImageFont.truetype(self.font_paths["regular"], 90),
            "forecast-hour": ImageFont.truetype(self.font_paths["regular"], 30),
            "forecast-temp": ImageFont.truetype(self.font_paths["regular"], 21),
            "sunrise": ImageFont.truetype(self.font_paths["semibold"], 21)
        }

        self.im = Image.new('L', (self.WIDTH, self.HEIGHT), 255)
        self.cv = ImageDraw.Draw(self.im)
        self.cv.text((self.WIDTH / 2, self.HEIGHT / 2), "Initializing ...", 0, font=self.fonts["small-destination"], anchor="mm", align="center")

        if DEBUG:
            self.root = tk.Tk()
            self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}")
            self.tkimg = ImageTk.PhotoImage(self.im)
            self.label = tk.Label(self.root, image=self.tkimg)
            self.label.pack()

        else:
            self.epd = epd7in5_HD.EPD()
            self.epd.init()
            self.epd.Clear()
            self.swap()

        self.transit = departures.DepartureRetainer()
        self.last_forecast = datetime.now(pytz.utc) - relativedelta(hours=24)
        self.forecast = []
        self.claim = ""

    def refresh(self):
        logging.info("Refreshing")

        self.im = Image.new('L', (self.WIDTH, self.HEIGHT), 255)
        self.cv = ImageDraw.Draw(self.im)

        now = datetime.now(pytz.utc)
        if now - relativedelta(minutes=20) > self.last_forecast:
            self.forecast = wetter.fetch_forecast()
            self.claim = departures.bvg_claim()
            self.last_forecast = now

        is_night = self.draw_departure_board((91, 28))

        if not is_night:
            self.draw_clock((195, 42))
            self.draw_forecast((63, 160))
        else:
            self.draw_background()
            self.draw_clock((445, 373), sunrise=True)

        self.swap()

        if DEBUG:
            self.root.after(1000 * REFRESH, self.refresh)

    def loop(self):
        if DEBUG:
            self.root.after(100, self.refresh)
            self.root.mainloop()

        else:
            while True:
                self.refresh()
                sleep(REFRESH)

    def swap(self):
        logging.info("Swapping")

        if DEBUG:
            self.tkimg = ImageTk.PhotoImage(self.im)
            self.label.configure(image=self.tkimg)
        else:
            self.epd.display(self.epd.getbuffer(self.im))

    def draw_departure_board(self, offset):
        depts = self.transit.get_display_data()

        empty = len(depts) == 0
        night = empty or depts[0]["line"] == "N6"
        if empty:
            logging.info(f"Setting night mode because there are no departures")
        elif night:
            logging.info("Setting to night mode because N6 was seen")

        x_pos = offset[0]
        y_pos = offset[1]

        if not night:
            x_pos += 269
            y_pos += 15

        for d in depts:
            self.draw_line(d["product"], d["line"], d["destination"], d["departures"], (x_pos, y_pos), wide=night)

            two_ring = False
            for (i, c) in enumerate(d["connections"]):
                if c is None:
                    continue

                if i == 0:
                    y_pos += 57
                elif not two_ring:
                    y_pos += 45

                if c["line"] == "S42" and len(d["connections"]) - 2 == i:
                    two_ring = True

                if two_ring:
                    width = 225
                else:
                    width = 450

                if two_ring and c["line"] != "S42":
                    two_ring = False
                    x_offset = 225
                else:
                    x_offset = 0

                self.draw_line(c["product"], c["line"], c["destination"], [c["stopover"]], (x_pos + x_offset, y_pos), True, wide=night, width_preset=width)

            y_pos += 68

        if not night and len(depts) > 0:
            icon = remove_transparency(Image.open(f"img/bvg@2x-8.png")).resize((40,36))
            self.im.paste(icon, (x_pos, y_pos - 8))
            self.cv.text((x_pos + 61, y_pos + 16), self.claim, 0, font=self.fonts["claim"], anchor="ls", align="left")

        return night

    def draw_line(self, product, line, destination, departures, pos, correspondance=False, wide=False, width_preset=450):
        orig_x = pos[0]
        if correspondance:
            pos = (pos[0] + 52, pos[1])

        dimensions = self.draw_line_indicator(product, line, pos, (not correspondance) or wide, correspondance)
        start_x = pos[0] + dimensions[0]

        if correspondance:
            start_x += 13
            dst_font = "small-destination"
            tme_font = "small-arrival"
        else:
            start_x += 19
            dst_font = "large-destination"
            tme_font = "large-arrival"

        if wide:
            width = 676
        else:
            width = width_preset

        self.cv.text((start_x, pos[1] + round(dimensions[1] * 0.869143)), destination, 0, font=self.fonts[dst_font], anchor="ls", align="left")
        self.cv.text((width + orig_x, pos[1] + round(dimensions[1] * 0.869143)), ", ".join(departures), 0, font=self.fonts[tme_font], anchor="rs", align="right")

    def draw_line_indicator(self, product, line, pos, compact=False, small=True):
        if small:
            height = 27
            font = "small-line"
        else:
            height = 35
            font = "large-line"

        if compact:
            width = round(height * 1.171428517)
        else:
            width = round(height * 1.592592593)

        if product == "suburban":
            self.cv.ellipse([pos, (pos[0] + height, pos[1] + height)], fill=0)
            self.cv.ellipse([(pos[0] + width - height, pos[1]), (pos[0] + width, pos[1] + height)], fill=0)
            self.cv.rectangle([(pos[0] + height / 2, pos[1]), (pos[0] + width - height / 2, pos[1] + height)], fill=0)
        else:
            fill = 0
            outline = None
            if product != "subway" and product != "tram":
                fill = 255
                outline = 0

            self.cv.rectangle([pos, (pos[0] + width, pos[1] + height)], fill=fill, outline=outline, width=2)

        fill = 255
        if product != "subway" and product != "tram" and product != "suburban":
            fill = 0

        if line == "S41" or line == "S42":
            icon = remove_transparency(Image.open(f"img/{line}@2x-8.png"), (0, 0, 0)).resize((15,17))
            self.im.paste(icon, (pos[0] + round(width / 2 - 7.5), pos[1] + round(height * 0.185185)))
        else:
            self.cv.text((pos[0] + ceil(width / 2 + .5), pos[1] + round(height * 0.814815)), line, fill, font=self.fonts[font], anchor="ms", align="center")
        return (width, height)

    # pos is the top center point
    def draw_clock(self, pos, sunrise=False):
        clock_y = pos[1] + 51
        self.cv.text((pos[0], clock_y), datetime.now().strftime("%H:%M"), 0, font=self.fonts["clock"], anchor="ms", align="center")
        self.cv.text((pos[0], clock_y + 32), datetime.now().strftime("%A, %x"), 0, font=self.fonts["date"], anchor="ms", align="center")

        if sunrise:
            icon = remove_transparency(Image.open(f"img/sunrise.png")).resize((52, 50))
            self.im.paste(icon, (pos[0] - 52, pos[1] + 100))
            self.cv.text((pos[0] - 2, pos[1] + 133), sun(wetter.city.observer, date=datetime.now(pytz.utc), tzinfo=wetter.city.timezone)["sunrise"].strftime("%H:%M"), 0, font=self.fonts["sunrise"], anchor="ls", align="left")

    def draw_forecast(self, pos):
        self.draw_hero_forecast(pos)
        self.draw_hourly_forecast((pos[0] + 45, pos[1] + 129))

    def draw_hero_forecast(self, pos):
        if len(self.forecast) <= 0:
            return

        forecast = self.forecast[0]
        icon = remove_transparency(Image.open(f"img/{wetter.get_icon(forecast)}.png")).resize((110,110))
        self.im.paste(icon, pos)

        self.cv.text((pos[0] + 115, pos[1] + 88), f"{round(forecast['temperature'])}°", 0, font=self.fonts["temperature"], anchor="ls", align="left")

    def draw_hourly_forecast(self, pos):
        if len(self.forecast) <= 1:
            return

        pos_y = pos[1]
        for f in self.forecast[1:5]:
            self.cv.text((pos[0] - 10, pos_y + 37), f["time"].strftime("%H Uhr"), 0, font=self.fonts["forecast-hour"], anchor="ls", align="left")
            icon = remove_transparency(Image.open(f"img/{wetter.get_icon(f)}.png")).resize((48,48))
            self.im.paste(icon, (pos[0] + 98, pos_y + 3))
            self.cv.text((pos[0] + 180, pos_y + 37), f"{round(f['temperature'])}°", 0, font=self.fonts["forecast-temp"], anchor="rs", align="right")
            pos_y += 58

    def draw_background(self):
        bg_height = round(self.HEIGHT * 0.65)
        background = Image.new('RGBA', (self.WIDTH, bg_height), (255, 255, 255, 0))

        tv_tower = Image.open("img/fernsehturm-8.png")
        background.paste(tv_tower, (round(self.WIDTH * 0.845), bg_height - 218))

        moon_phase = wetter.get_moon_phase(datetime.now(pytz.utc)).graphic_string()

        if moon_phase != "new":
            moon = Image.open(f"img/moon_l_{moon_phase}-8.png").resize((200, 200))
            background.paste(moon, (round(self.WIDTH * 0.0625), -20))

        if len(self.forecast) > 0:
            cloud_cover = self.forecast[0]["cloud_cover"]
            cloud_amount = max(min(7*cloud_cover/73 - 84/73, 7), 0)
            cloud = Image.open(f"img/cloud-8.png")
            cloud_dimensions = (147, 86)
            cloud_band = 48

            for _ in range(round(cloud_amount)):
                scale = random() * .3 + .85
                left = round(random() * self.WIDTH - cloud_dimensions[0] / 2)
                offset = round(random() * cloud_band)
                resized = cloud.resize((round(cloud_dimensions[0] * scale), round(cloud_dimensions[1] * scale)))
                background.paste(resized, (left, 15+offset), resized.convert('RGBA'))

        self.im.paste(remove_transparency(background), (0, self.HEIGHT - bg_height))

def remove_transparency(im, bg_colour=(255, 255, 255)):
    # Only process if image has transparency (http://stackoverflow.com/a/1963146)
    if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):

        # Need to convert to RGBA if LA format due to a bug in PIL (http://stackoverflow.com/a/1963146)
        alpha = im.convert('RGBA').split()[-1]

        # Create a new background image of our matt color.
        # Must be RGBA because paste requires both images have the same format
        # (http://stackoverflow.com/a/8720632  and  http://stackoverflow.com/a/9459208)
        bg = Image.new("RGBA", im.size, bg_colour + (255,))
        bg.paste(im, mask=alpha)
        return bg

    else:
        return im

try:
    app = App()
    app.loop()

except Exception:
    logging.exception("Fatal exception")

    if not DEBUG:
        epd7in5_HD.epdconfig.module_exit()
