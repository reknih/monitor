import feedparser
import time

def parse_feed(url):
    d = feedparser.parse(url)

    return [{
        "title": entry["title"],
        "time": time.strftime("%H:%M", entry["updated_parsed"]),
        "summary": entry["summary"]
    } for entry in d.entries[:3]]

def tagesschau():
    return parse_feed("https://www.tagesschau.de/xml/atom/")

def tagesspiegel():
    return parse_feed("https://www.tagesspiegel.de/contentexport/feed/home")

def new_york_times():
    return parse_feed("https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml")

def bz_local():
    return parse_feed("https://www.berliner-zeitung.de/feed.id_mensch_und_metropole.xml")

# print(new_york_times())
