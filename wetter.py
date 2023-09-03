from datetime import datetime, timezone
from enum import Enum
import logging
import os
import sys

from astral import LocationInfo, moon
from astral.sun import sun, golden_hour
from dateutil.relativedelta import relativedelta
from wetterdienst.provider.dwd.mosmix import DwdMosmixRequest, DwdMosmixType
import pytz

city = LocationInfo("Berlin", "Germany", "Europe/Berlin", 52.562923, 13.328471)


class PrecipitationType(Enum):
    RAIN = 0
    DRIZZLE = 1
    FREEZING = 2
    SNOW = 3


class MoonPhase(Enum):
    NEW_MOON = 0
    WAXING_CRESCENT = 1
    FIRST_QUARTER = 2
    WAXING_GIBBOUS = 3
    FULL_MOON = 4
    WANING_GIBBOUS = 5
    THIRD_QUARTER = 6
    WANING_CRESCENT = 7

    def graphic_string(self):
        if self.value <= 0 or self.value > 7:
            return "new"
        elif self.value == 1:
            return "xcrescent"
        elif self.value == 2:
            return "fquarter"
        elif self.value == 3:
            return "xgibbous"
        elif self.value == 4:
            return "full"
        elif self.value == 5:
            return "ngibbous"
        elif self.value == 6:
            return "tquarter"
        elif self.value == 7:
            return "ncrescent"


def get_moon_phase(date):
    angle = moon.phase(date)

    if angle < 1.75 or angle >= 26.25:
        return MoonPhase.NEW_MOON
    elif angle < 5.25:
        return MoonPhase.WAXING_CRESCENT
    elif angle < 8.75:
        return MoonPhase.FIRST_QUARTER
    elif angle < 12.25:
        return MoonPhase.WAXING_GIBBOUS
    elif angle < 15.75:
        return MoonPhase.FULL_MOON
    elif angle < 19.25:
        return MoonPhase.WANING_GIBBOUS
    elif angle < 22.75:
        return MoonPhase.THIRD_QUARTER
    else:
        return MoonPhase.WANING_CRESCENT


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
    df = response.df.to_pandas()
    now = datetime.now(pytz.utc)

    sys.stderr = prev_stderr
    logger.setLevel(prev_level)

    twentyfour = df[df["date"] <= now + relativedelta(hours=25)]
    twentyfour = twentyfour[twentyfour["date"] >= now]

    cloud_selector = twentyfour["parameter"] == "cloud_cover_effective"
    tempr_selector = twentyfour["parameter"] == "temperature_air_mean_200"
    fog_selector = twentyfour["parameter"] == "probability_fog_last_1h"
    thunder_selector = twentyfour["parameter"] == "probability_thunder_last_1h"

    prec_selector = twentyfour["parameter"] == "probability_precipitation_last_1h"

    # Select precipitation type based on which of these is maximal
    rain_selector = twentyfour["parameter"] == "probability_precipitation_liquid_last_1h"
    snow_selector = twentyfour["parameter"] == "probability_precipitation_solid_last_1h"
    frez_selector = twentyfour["parameter"] == "probability_precipitation_freezing_last_1h"
    drizzle_selector = twentyfour["parameter"] == "probability_drizzle_last_1h"

    forecast = []

    for i in range(min(len(twentyfour[cloud_selector]), 24)):
        temp_record = twentyfour[tempr_selector]
        time = temp_record["date"].iloc[i]
        s = sun(city.observer, date=time, tzinfo=city.timezone)

        day = s["dawn"] < time and s["dusk"] > time

        current = {
            "temperature": round(temp_record["value"].fillna(0.0).iloc[i] - 273.15, 1),
            "cloud_cover": twentyfour[cloud_selector]["value"].fillna(0.0).iloc[i],
            "foggy": twentyfour[fog_selector]["value"].fillna(0.0).iloc[i] >= 50,
            "thunderstorm": twentyfour[thunder_selector]["value"].fillna(0.0).iloc[i] >= 60,
            "daylight": day,
            "moon": get_moon_phase(time),
            "time": time,
        }

        prec = {
            "probability": twentyfour[prec_selector]["value"].fillna(0.0).iloc[i],
            "kind": PrecipitationType.RAIN
        }

        rain_prob = twentyfour[rain_selector]["value"].fillna(0.0).iloc[i]
        snow_prob = twentyfour[snow_selector]["value"].fillna(0.0).iloc[i]
        frez_prob = twentyfour[frez_selector]["value"].fillna(0.0).iloc[i]
        drizzle_prob = twentyfour[drizzle_selector]["value"].fillna(
            0.0).iloc[i]

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
