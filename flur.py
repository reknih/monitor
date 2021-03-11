import locale
import departures
import wetter
import pytz
from astral.sun import sun
from datetime import datetime

from math import ceil

import tkinter as tk
from PIL import Image, ImageDraw, ImageTk, ImageFont

locale.setlocale(locale.LC_ALL, 'de_DE')

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

class App:
    WIDTH, HEIGHT = (800,600)
    def __init__(self):
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
        self.night = False

        self.im = Image.new('L', (self.WIDTH, self.HEIGHT), 255)
        self.cv = ImageDraw.Draw(self.im)
        self.transit = departures.DepartureRetainer()
        self.forecast = []

        self.night = self.update_departure_board((61, 38))
        if not self.night:
            self.draw_clock((161, 63))
            self.draw_forecast((59, 193))
        else:
            self.draw_clock((400, 396), sunrise=True)

        self.window = tk.Tk()
        self.window.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.tkimg = ImageTk.PhotoImage(self.im)
        tk.Label(self.window, image=self.tkimg).pack()
        self.window.mainloop()

    def update_departure_board(self, offset):
        depts = self.transit.get_display_data()
        night = len(depts) == 0 or depts[0]["line"] == "N6"
        x_pos = offset[0]
        y_pos = offset[1]

        if not night:
            x_pos += 269
            y_pos += 35

        for d in depts:
            self.line(d["product"], d["line"], d["destination"], d["departures"], (x_pos, y_pos), wide=night)

            for (i, c) in enumerate(d["connections"]):
                if i == 0:
                    y_pos += 57
                else:
                    y_pos += 45

                self.line(c["product"], c["line"], c["destination"], [c["stopover"]], (x_pos, y_pos), True)

            y_pos += 68

        if not night and len(depts) > 0:
            y_pos -= 8
            icon = remove_transparency(Image.open(f"img/bvg@2x-8.png")).resize((40,36))
            self.im.paste(icon, (x_pos, y_pos))
            self.cv.text((x_pos + 61, y_pos + 24), departures.bvg_claim(), 0, font=self.fonts["claim"], anchor="ls", align="left")

        return night

    def line(self, product, line, destination, departures, pos, correspondance=False, wide=False):
        orig_x = pos[0]
        if correspondance:
            pos = (pos[0] + 52, pos[1])

        dimensions = self.line_indicator(product, line, pos, (not correspondance) or wide, correspondance)
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
            width = 415

        self.cv.text((start_x, pos[1] + round(dimensions[1] * 0.869143)), destination, 0, font=self.fonts[dst_font], anchor="ls", align="left")
        self.cv.text((width + orig_x, pos[1] + round(dimensions[1] * 0.869143)), ", ".join(departures), 0, font=self.fonts[tme_font], anchor="rs", align="right")

    def line_indicator(self, product, line, pos, compact=False, small=True):
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
            self.im.paste(icon, (pos[0] - 52, pos[1] + 116))
            self.cv.text((pos[0] - 2, pos[1] + 149), sun(wetter.city.observer, date=datetime.now(pytz.utc), tzinfo=wetter.city.timezone)["sunrise"].strftime("%H:%M"), 0, font=self.fonts["sunrise"], anchor="ls", align="left")

    def draw_forecast(self, pos):
        self.forecast = wetter.fetch_forecast()
        self.draw_hero_forecast((pos[0] - 18, pos[1]))
        self.draw_hourly_forecast((pos[0], pos[1] + 122))

    def draw_hero_forecast(self, pos):
        if len(self.forecast) <= 0:
            return

        forecast = self.forecast[0]
        icon = remove_transparency(Image.open(f"img/{wetter.get_icon(forecast)}.png")).resize((110,110))
        self.im.paste(icon, (pos[0], pos[1]))

        self.cv.text((pos[0] + 115, pos[1] + 88), f"{round(forecast['temperature'])}°", 0, font=self.fonts["temperature"], anchor="ls", align="left")

    def draw_hourly_forecast(self, pos):
        if len(self.forecast) <= 1:
            return

        pos_y = pos[1]
        for f in self.forecast[1:5]:
            self.cv.text((pos[0] - 10, pos_y + 37), f["time"].strftime("%H Uhr"), 0, font=self.fonts["forecast-hour"], anchor="ls", align="left")
            icon = remove_transparency(Image.open(f"img/{wetter.get_icon(f)}.png")).resize((48,48))
            self.im.paste(icon, (pos[0] + 100, pos_y))
            self.cv.text((pos[0] + 175, pos_y + 37), f"{round(f['temperature'])}°", 0, font=self.fonts["forecast-temp"], anchor="rs", align="right")
            pos_y += 58

app = App()