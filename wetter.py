from datetime import datetime
from enum import Enum
import logging
import os
import sys

from astral.sun import sun, golden_hour
from dateutil.relativedelta import relativedelta
from wetterdienst.provider.dwd.mosmix import DwdMosmixRequest, DwdMosmixType
import pytz
import polars as pl
from astro import MoonPhase, get_moon_phase, city


class PrecipitationType(Enum):
    RAIN = 0
    DRIZZLE = 1
    FREEZING = 2
    SNOW = 3


def fetch_forecast():
    logging.info("Fetching forecast")

    logger = logging.getLogger()
    prev_stderr = sys.stderr
    prev_level = logger.level
    sys.stderr = open(os.devnull, 'w')
    logger.setLevel(logging.WARN)

    stations = DwdMosmixRequest(
        parameter="large", mosmix_type=DwdMosmixType.LARGE).filter_by_station_id(station_id=10382)
    response = next(stations.values.query())
    logging.info("Processing forecast")

    df = response.df
    now = datetime.now(pytz.utc)

    sys.stderr = prev_stderr
    logger.setLevel(prev_level)

    twentyfour = df.filter(pl.col("date") <= now + relativedelta(hours=25))
    twentyfour = twentyfour.filter(pl.col("date") >= now)

    cloud_selector = pl.col("parameter") == "cloud_cover_effective"
    tempr_selector = pl.col("parameter") == "temperature_air_mean_200"
    fog_selector = pl.col("parameter") == "probability_fog_last_1h"
    thunder_selector = pl.col("parameter") == "probability_thunder_last_1h"

    prec_selector = pl.col("parameter") == "probability_precipitation_last_1h"

    # Select precipitation type based on which of these is maximal
    rain_selector = pl.col(
        "parameter") == "probability_precipitation_liquid_last_1h"
    snow_selector = pl.col(
        "parameter") == "probability_precipitation_solid_last_1h"
    frez_selector = pl.col(
        "parameter") == "probability_precipitation_freezing_last_1h"
    drizzle_selector = pl.col("parameter") == "probability_drizzle_last_1h"

    forecast = []

    temp_record = twentyfour.filter(tempr_selector)
    cloud_record = twentyfour.filter(cloud_selector)["value"]
    fog_record = twentyfour.filter(fog_selector)["value"]
    thunder_record = twentyfour.filter(thunder_selector)["value"]
    rain_record = twentyfour.filter(rain_selector)["value"]
    snow_record = twentyfour.filter(snow_selector)["value"]
    frez_record = twentyfour.filter(frez_selector)["value"]
    drizzle_record = twentyfour.filter(drizzle_selector)["value"]

    for i in range(min(len(twentyfour.filter(cloud_selector)), 24)):
        time = temp_record["date"][i]

        s = sun(city.observer, date=time, tzinfo=city.timezone)

        day = s["dawn"] < time and s["dusk"] > time

        current = {
            "temperature": round(temp_record["value"][i] - 273.15, 1),
            "cloud_cover": cloud_record[i],
            "foggy": fog_record[i] >= 50,
            "thunderstorm": thunder_record[i] >= 60,
            "daylight": day,
            "moon": get_moon_phase(time),
            "time": time,
        }

        prec = {
            "probability": twentyfour.filter(prec_selector)["value"][i],
            "kind": PrecipitationType.RAIN
        }

        rain_prob = rain_record[i]
        snow_prob = snow_record[i]
        frez_prob = frez_record[i]
        drizzle_prob = drizzle_record[i]

        max_prob = max(rain_prob, snow_prob, frez_prob, drizzle_prob)

        if max_prob > rain_prob:
            if max_prob == snow_prob:
                prec["kind"] = PrecipitationType.SNOW
            elif max_prob == frez_prob:
                prec["kind"] = PrecipitationType.FREEZING
            elif max_prob == drizzle_prob:
                prec["kind"] = PrecipitationType.DRIZZLE

        current["precipitation"] = prec

        # Add information about golden hour if weather is nice
        if current["cloud_cover"] < 35 and current["precipitation"]["probability"] < 10:
            golden = golden_hour(city.observer, time, tzinfo=city.timezone)[0]
            if time <= golden and time + relativedelta(minutes=60) > golden:
                current["golden_hour"] = golden

        forecast.append(current)

    return forecast


def get_icon(forecast):
    # clear, cloudy, overcast, day, night
    sky_state = 0b00000

    if forecast["cloud_cover"] < 35:
        sky_state |= 0b10000
    elif forecast["cloud_cover"] > 65:
        sky_state |= 0b00100
    else:
        sky_state |= 0b01000

    if forecast["daylight"]:
        sky_state |= 0b00010
    else:
        sky_state |= 0b00001

    if forecast["thunderstorm"]:
        if sky_state & 0b11010:
            return "thunderstorm_day"
        elif sky_state & 0b11001 and forecast["moon"] != MoonPhase.FULL_MOON:
            return "thunderstorm_night"
        else:
            return "thunderstorm_overcast"

    if forecast["precipitation"]["probability"] >= 40:
        if sky_state & 0b11010:
            postfix = "day"
        elif sky_state & 0b11001 and forecast["moon"] != MoonPhase.FULL_MOON:
            postfix = "night"
        else:
            postfix = "overcast"

        if forecast["precipitation"]["kind"] == PrecipitationType.DRIZZLE:
            return f"drizzle_{postfix}"
        elif forecast["precipitation"]["kind"] == PrecipitationType.FREEZING:
            return f"freezing_{postfix}"
        elif forecast["precipitation"]["kind"] == PrecipitationType.SNOW:
            return f"snow_{postfix}"
        else:
            return f"rain_{postfix}"

    if forecast["foggy"]:
        return "fog"

    if sky_state & 0b11010 and "golden_hour" in forecast:
        return "golden_hour"

    if sky_state & 0b00010:
        if sky_state & 0b10000:
            return "sunny"
        else:
            return "cloudy_day"

    if sky_state & 0b00001:
        if sky_state & 0b10000:
            ms = forecast["moon"].graphic_string()
            return f"moon_{ms}"
        else:
            return "cloudy_night"

    return "overcast"

# for f in fetch_forecast():
#     print(f)
#     print(get_icon(f))
