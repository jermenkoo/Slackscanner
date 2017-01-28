import requests
import os

from flask import request, Flask

app = Flask(__name__)
API_KEY = "ha393385273835879384162930498674"


def get_airports():
    """Returns a dictionary IATA -> City from a file with airports."""
    iata_to_city = {}
    with open('./airports.txt') as f:
        for line in f.readlines():
            line = line.strip()

            if len(line) < 5:
                continue

            r = line.strip().split(',')[0]
            r = r.replace(' ', '')
            iata, city = r.split('-', 1)

            if iata_to_city.get(iata) is None:
                iata_to_city[iata] = city

    return iata_to_city


def find_airport_code_by_city(city):
    """Given a city name, returns the corresponding IATA airport code."""
    airports = get_airports()

    if city == 'London':
        return 'LHR'

    for airport_code in airports:
        if airports[airport_code].lower() == city.lower():
            return airport_code
    return None


def find_flights(code1, code2, outbound, inbound=None):
    def _poll_live_pricing(session_url):
        return requests.get("{}?apikey={}".format(session_url, API_KEY))

    data = {
        'country': 'UK',
        'currency': 'GBP',
        'locale': 'en-GB',
        'locationSchema': 'iata',
        'apikey': API_KEY,
        'grouppricing': 'on',
        'originplace': code1,
        'destinationplace': code2,
        'outbounddate': outbound,
        'includeBookingDetailsLink': 'false',
    }
    if inbound:
        data['inbounddate'] = inbound

    print(data)

    session_response = requests.post("http://business.skyscanner.net/apiservices/pricing/v1.0/?apikey={}&pageIndex=0&pageSize=10".format(API_KEY), data=data)
    session_url = session_response.headers['Location']

    print("Session URL from Skyscanner: {}".format(session_url))

    pricing_response = _poll_live_pricing(session_url)
    while pricing_response.status_code != 200:
        pricing_response = _poll_live_pricing(session_url)

    result = pricing_response.json()
    return result


def get_leg_information(everything, legId):
    if legId is None:
        return ""

    for leg in everything['Legs']:
        if leg['Id'] == legId:
            return "Departure: {} Arrival: {}".format(
                leg['Departure'],
                leg['Arrival']
            )


def get_flight_information(everything, out=None, inn=None):
    print("[get_flight_information]")

    outbound = get_leg_information(everything, out)
    inbound = get_leg_information(everything, inn)

    return "\tOutbound: " + outbound + "\n" + "\tInbound: " + inbound + "\n"


@app.route('/hello', methods=['POST'])
def hello():
    """Slack integration endpoint for SkyScanner API."""
    cities = get_airports().values()
    print(request.form)
    user_query = request.form.get('text')
    tokenized_query = user_query.split(' ')

    city1, city2 = tokenized_query[:2]
    code1, code2 = map(find_airport_code_by_city, (city1, city2))
    date1 = tokenized_query[2]
    date2 = None if len(tokenized_query) == 3 else tokenized_query[3]

    all_flights = find_flights(code1, code2, date1, date2)
    my_flight = all_flights['Itineraries'][0]
    out = my_flight.get('OutboundLegId')
    inn = my_flight.get('InboundLegId')

    res = get_flight_information(all_flights, out, inn)

    PUSHER_APP_ID = "cd8cd55a-1363-4605-bd0f-8cc1a8253b9d"
    PUSHER_FED_NM = "skyscanner"

    payload = "{\"items\":[{\"search\":\"%s\"}]}" % ("from {} to {} on {}".format(city1, city2, date1))

    q = requests.post(
        "https://api.private-beta-1.pusherplatform.com:443/apps/{}/feeds/{}".format(PUSHER_APP_ID, PUSHER_FED_NM),
        data=payload,
        verify=False
    )

    requests.post(
        request.form.get('response_url'),
        headers={
            'Content-Type': 'application/json'
        },
        data=str(
            {
                'response_type': 'in_channel',
                'text': 'Flights found from: *{}* to: *{}*:\n'.format(code1, code2) + res
            },
        ),
        verify=False
    )

    return 'A response.'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
