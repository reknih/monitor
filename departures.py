from datetime import datetime
import asyncio
import logging
import random
import re

from concurrent.futures import ThreadPoolExecutor
from dateutil import parser
from dateutil.relativedelta import relativedelta
import pytz
import requests

def normalize_station_name(name):
    name = re.sub(r"^(U|S)(\+U)? ", "", name)
    name = re.sub(r"^Alt-", "", name)
    name = re.sub(r"(,|(\s->)) .*$", "", name)
    name = re.sub(r"/\s?\w+$", "", name)
    name = re.sub(r"\sHauptbahnhof$", "", name)
    name = re.sub(r"\sHbf\.?$", "", name)
    name = re.sub(r"\sStr((\.)|aße)$", " Str.", name)
    name = re.sub(r"^Friedrich-Ludwig-Jahn-Sportpark", "Friedr.-L.-Jahn-Sportp.", name)
    name = re.sub(r"^Rathaus ", "", name)
    name = re.sub(r"^Betriebshof ", "BVG-Hof ", name)
    return name

def group_by_direction(departures):
    by_direction = {}
    for departure in departures:
        dirct = normalize_station_name(departure["direction"])

        if dirct in by_direction:
            by_direction[dirct].append(departure)
        else:
            by_direction[dirct] = [departure]
    return by_direction

def dept_to_str(departure, now):
    mmax = relativedelta(minutes=25)
    mmin = relativedelta(seconds=60)
    departure = parser.parse(departure)
    if departure <= now+mmin:
        return "jetzt"
    elif departure <= now+mmax:
        to_go = relativedelta(departure, now)
        return f"{to_go.minutes}m"
    else:
        return departure.astimezone().strftime("%H:%M")

def delta_to_str(delta):
    if (delta.minutes == 0 or (delta.minutes == 1 and delta.seconds < 30)) and delta.hours == 0 and delta.days == 0:
        return f"knapp"

    if delta.hours == 0 and delta.days == 0:
        return f"{delta.minutes}m"

    if delta.days == 0:
        return f"{delta.hours}h {delta.minutes}m"

    return "ewig"


# U Afrikanische Straße
home_id = "900000011102"

frator_id = "900000120008"
hansaplatz_id = "900000003101"
prenzlauer_id = "900000110002"
stahlheimer_id = "900000110015"
bekassinenweg_id = "900000091156"
westend_id = "900000026207"

anklamer_lat = "52.533902"
anklamer_lng = "13.393388"
anklamer_addr = "Anklamer+Str.+60"

terminus_north = ["Tegel", "Borsigwerke", "Kurt-Schumacher-Platz"]
terminus_south = ["Mariendorf", "Seestraße", "Wedding", "Naturkundemuseum", "Hallesches Tor", "Mehringdamm", "Platz der Luftbrücke", "Tempelhof"]

def fetch(session, url, timeout, default=None):
    try:
        response = session.get(url, timeout=timeout)
    except requests.exceptions.ReadTimeout:
        logging.warn("Failed to fetch due to timeout")
        return default

    if response.status_code == 200:
        return response.json()

    return default

def get_data(session=None):
    try:
        if session != None:
            response = session.get(f"https://v5.bvg.transport.rest/stops/{home_id}/departures?language=de", timeout=6.1)
            # response = session.get(f"https://v5.bvg.transport.rest/stops/{home_id}/departures?language=de&when=2021-03-24T01:50%2B01:00", timeout=5)
        else:
            response = requests.get(f"https://v5.bvg.transport.rest/stops/{home_id}/departures?language=de", timeout=6.1)
    except requests.exceptions.ReadTimeout:
        logging.warn("Failed to fetch departures due to timeout")
        return None

    if response.status_code == 200:
        return response.json()

    return None

def get_change_time(session, destination, allow_suburban, allow_tram, allow_bus, transfers=1):
    query = f"https://v5.bvg.transport.rest/journeys?from={home_id}&to={destination}&transfers={transfers}&startWithWalking=false&results=2&ferry=false&express=false&regional=false"

    if not allow_suburban:
        query += "&suburban=false"

    if not allow_tram:
        query += "&tram=false"

    if not allow_bus:
        query += "&bus=false"

    return fetch(session, query, 3.1)

def get_change_time_home(session, lat, long, name, allow_suburban, allow_tram, allow_bus):
    query = f"https://v5.bvg.transport.rest/journeys?from={home_id}&to.latitude={lat}&to.longitude={long}&to.address={name}&transfers=1&startWithWalking=false&results=2&ferry=false&express=false&regional=false"

    if not allow_suburban:
        query += "&suburban=false"

    if not allow_tram:
        query += "&tram=false"

    if not allow_bus:
        query += "&bus=false"

    return fetch(session, query, 3.1)

def process_change_time(response):
    legs = None
    for journey in response["journeys"]:
        if parser.parse(get_departure(journey["legs"][0])) > datetime.now(pytz.utc) + relativedelta(seconds=30):
            legs = journey["legs"]
            break

    if legs == None:
        return None

    next_leg = 1
    for i in range(1, len(legs)):
        if "walking" in legs[i] and legs[i]["walking"]:
            next_leg = i+1
        else:
            break

    if next_leg >= len(legs):
        return None

    arrival = parser.parse(get_arrival(legs[0]))
    change_station = normalize_station_name(legs[0]["destination"]["name"])
    departure = parser.parse(get_departure(legs[next_leg]))
    line = legs[next_leg]["line"]["name"]

    if line == "S41" or line == "S42":
        destination = "Ring"
    else:
        destination = normalize_station_name(legs[next_leg]["direction"])

    delta = delta_to_str(relativedelta(departure, arrival))
    if delta == "ewig":
        return None

    return {
        "destination": destination,
        "line": line,
        "arrival": arrival,
        "departure": departure,
        "stopover": delta,
        "change_station": change_station,
        "product": legs[next_leg]["line"]["product"]
    }

def get_departure(leg):
    return leg["departure"] or leg["plannedDeparture"]

def get_arrival(leg):
    return leg["arrival"] or leg["plannedArrival"]

def process_departures(departures):
    if departures is None:
        return {}

    subways = group_by_direction([departure for departure in departures if departure["line"]["product"] == "subway"])
    busses = group_by_direction([departure for departure in departures if departure["line"]["product"] == "bus"])

    now = datetime.now(pytz.utc)
    results = {k: { "product": "subway", "line": v[0]["line"]["name"], "departures": [dept_to_str(train["when"], now) for train in v if parser.parse(train["when"]) > now] } for (k,v) in subways.items()}
    busses = {k: { "product": "bus", "line": v[0]["line"]["name"], "departures": [dept_to_str(train["when"], now) for train in v if parser.parse(train["when"]) > now] } for (k,v) in busses.items()}

    if len(results) < 2:
        for (k, v) in busses.items():
            if k not in results:
                results[k] = v

    return results

class DepartureRetainer():
    def __init__(self):
        self.last_refresh = datetime.now(pytz.utc) - relativedelta(hours=24)
        self.departures_raw = []
        self.subway_departures = {}
        self.inbound_connections_raw = [None] * 6
        self.inbound_connections = []
        self.outbound_connections_raw = [None] * 1
        self.outbound_connections = []

    async def refresh_data(self):
        now = datetime.now(pytz.utc)
        if now - relativedelta(seconds=50) < self.last_refresh and len(self.departures_raw) > 0:
            return

        logging.info("Fetching departures")

        with requests.Session() as session:
            departures = get_data(session=session)
            if departures is not None:
                self.departures_raw = departures

            self.subway_departures = process_departures(self.departures_raw)

            with ThreadPoolExecutor(max_workers=10) as executor:
                loop = asyncio.get_event_loop()
                connections = [
                    asyncio.gather(*[
                        loop.run_in_executor(executor, get_change_time, *(session, hansaplatz_id, False, False, False)),
                        loop.run_in_executor(executor, get_change_time_home, *(session, anklamer_lat, anklamer_lng, anklamer_addr, False, True, False)),
                        loop.run_in_executor(executor, get_change_time, *(session, stahlheimer_id, False, True, False)),
                        loop.run_in_executor(executor, get_change_time, *(session, frator_id, False, False, False)),
                        loop.run_in_executor(executor, get_change_time, *(session, westend_id, True, False, False)),
                        loop.run_in_executor(executor, get_change_time, *(session, prenzlauer_id, True, False, False))
                    ]), asyncio.gather(*[
                        loop.run_in_executor(executor, get_change_time, *(session, bekassinenweg_id, False, False, True))
                    ])
                ]

                response = await asyncio.gather(*connections)
                inbound = response[0]
                outbound = response[1]

                for (i, data) in enumerate(inbound):
                    if data is not None:
                        self.inbound_connections_raw[i] = data

                self.inbound_connections = [process_change_time(x) for x in self.inbound_connections_raw if x is not None]

                for (i, data) in enumerate(outbound):
                    if data is not None:
                        self.outbound_connections_raw[i] = data

                self.outbound_connections = [process_change_time(x) for x in self.outbound_connections_raw if x is not None]

        self.last_refresh = now

    def get_display_data(self):
        loop = asyncio.get_event_loop()
        future = asyncio.ensure_future(self.refresh_data())
        loop.run_until_complete(future)
        result = []
        night = False

        for terminus in terminus_south:
            if terminus in self.subway_departures:
                route = self.subway_departures[terminus]
                route["destination"] = terminus

                if route["line"] == "N6":
                    route["connections"] = []
                    night = True
                else:
                    route["connections"] = self.inbound_connections

                result.append(route)
                break

        for terminus in terminus_north:
            if terminus in self.subway_departures:
                route = self.subway_departures[terminus]
                route["destination"] = terminus

                if route["line"] == "N6":
                    night = True

                route["connections"] = self.outbound_connections
                result.append(route)
                break

        if len(result) == 0:
            logging.info("No departures")
            night = True

        if night:
            result.reverse()

        return result, night

def bvg_claim():
    objekt = ["Dich", "Uns", "Bier", "Baden", "Mittagessen", "es hier", "uns vier", "Papier", "Käse", "Wache", "den Alex", "Free Jazz", "uns alle", "Föderalismus", "Wowereits Vermächtnis", "Chillisauce", "Asphalt", "es bald", "im Wald"]
    verb = ["lieben", "schieben", "sieben", "ließen", "berieben", "übertrieben", "beschrieben", "besiedeln", "ziegeln", "zerrieben", "vertiefen", "fließen", "gießen", "siezen", "striezen", "stibitzen", "verdünisieren"]
    complete = ["statisch typisieren", "an Ort und Stelle blieben"]

    state = random.random()
    if state < 0.45:
        return f"Weil wir Dich {verb[random.randrange(0, len(verb))]}"
    elif state < 0.90:
        return f"Weil wir {objekt[random.randrange(0, len(objekt))]} lieben"
    elif state < 0.96:
        return f"Weil wir {objekt[random.randrange(0, len(objekt))]} {verb[random.randrange(0, len(verb))]}"
    else:
        return f"Weil wir {complete[random.randrange(0, len(complete))]}"

# print(process_departures(get_data()))
# print(process_change_time(get_change_time(hansaplatz_id, False, False, False)))
# print(process_change_time(get_change_time_home(anklamer_lat, anklamer_lng, anklamer_addr, False, True, False)))

# depts = DepartureRetainer()
# print(depts.get_display_data())
