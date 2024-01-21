from enum import Enum
from astral import moon, LocationInfo

city = LocationInfo("Berlin", "Germany", "Europe/Berlin", 52.562923, 13.328471)


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
