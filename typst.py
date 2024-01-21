import os
import requests

# Fetch the secret Typst route and return how many users are online


def get_typst_online():
    secret_url = os.environ.get("MONITOR_TYPST_SECRET_URL")
    if secret_url is None:
        return None

    try:
        resp = requests.get(secret_url)
        if resp.status_code != 200:
            return None

        # The response is returned as a string in the X clients, Y projects
        # format. We only care about the X clients part.
        return int(resp.text.split()[0])
    except Exception:
        return None


# Return the number of GitHub stars for the typst repository
def get_typst_stars():
    api_key = os.environ.get("MONITOR_GITHUB_API_KEY")

    try:
        url = "https://api.github.com/repos/typst/typst"
        resp = requests.get(url, headers={
                            "Authorization": "token " + api_key}) if api_key else requests.get(url)

        if resp.status_code != 200:
            return None

        return resp.json()["stargazers_count"]
    except Exception:
        return None
