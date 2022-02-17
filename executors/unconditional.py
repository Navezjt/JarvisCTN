import re
import sys
import webbrowser

import inflect
import requests
import wolframalpha
import wordninja
from geopy.distance import geodesic
from search_engine_parser.core.engines.google import Search as GoogleSearch
from search_engine_parser.core.exceptions import NoResultsOrTrafficError

from modules.audio import listener, speaker
from modules.conditions import keywords
from modules.utils import globals

env = globals.ENV


def alpha(text: str) -> bool:
    """Uses wolfram alpha API to fetch results for uncategorized phrases heard.

    Args:
        text: Takes the voice recognized statement as argument.

    Notes:
        Handles broad ``Exception`` clause raised when Full Results API did not find an input parameter while parsing.

    Returns:
        bool:
        Boolean True if wolfram alpha API is unable to fetch consumable results.

    References:
        `Error 1000 <https://products.wolframalpha.com/show-steps-api/documentation/#:~:text=(Error%201000)>`__
    """
    if not env.wolfram_api_key:
        return False
    alpha_client = wolframalpha.Client(app_id=env.wolfram_api_key)
    try:
        res = alpha_client.query(text)
    except Exception:  # noqa
        return True
    if res['@success'] == 'false':
        return True
    else:
        try:
            response = next(res.results).text.splitlines()[0]
            response = re.sub(r'(([0-9]+) \|)', '', response).replace(' |', ':').strip()
            if response == '(no data available)':
                return True
            speaker.speak(text=response)
        except (StopIteration, AttributeError):
            return True


def google(query: str, suggestion_count: int = 0) -> None:
    """Uses Google's search engine parser and gets the first result that shows up on a Google search.

    Notes:
        - If it is unable to get the result, Jarvis sends a request to ``suggestqueries.google.com``
        - This is to rephrase the query and then looks up using the search engine parser once again.
        - ``suggestion_count`` is used to limit the number of times suggestions are used.
        - ``suggestion_count`` is also used to make sure the suggestions and parsing don't run on an infinite loop.
        - This happens when ``google`` gets the exact search as suggested ones which failed to fetch results earlier.

    Args:
        suggestion_count: Integer value that keeps incrementing when ``Jarvis`` looks up for suggestions.
        query: Takes the voice recognized statement as argument.
    """
    results = []
    try:
        google_results = GoogleSearch().search(query, cache=False)
        results = [result['titles'] for result in google_results]
    except NoResultsOrTrafficError:
        suggest_url = "https://suggestqueries.google.com/complete/search"
        params = {
            "client": "firefox",
            "q": query,
        }
        response = requests.get(suggest_url, params)
        if not response:
            return
        try:
            suggestion = response.json()[1][1]
            suggestion_count += 1
            if suggestion_count >= 3:  # avoids infinite suggestions over the same suggestion
                speaker.speak(text=response.json()[1][0].replace('=', ''),
                              run=True)  # picks the closest match and Google's it
                return
            else:
                google(suggestion, suggestion_count)
        except IndexError:
            return

    if not results:
        return

    for result in results:
        if len(result.split()) < 3:
            results.remove(result)

    if not results:
        return

    results = results[0:3]  # picks top 3 (first appeared on Google)
    results.sort(key=lambda x: len(x.split()), reverse=True)  # sorts in reverse by the word count of each sentence
    output = results[0]  # picks the top most result
    if '\n' in output:
        required = output.split('\n')
        modify = required[0].strip()
        split_val = ' '.join(wordninja.split(modify.replace('.', 'rEpLaCInG')))
        sentence = split_val.replace(' rEpLaCInG ', '.')
        repeats = []  # Captures repeated words by adding them to the empty list
        [repeats.append(word) for word in sentence.split() if word not in repeats]
        refined = ' '.join(repeats)
        output = refined + required[1] + '.' + required[2]
    output = output.replace('\\', ' or ')
    match_word = re.search(r'(\w{3},|\w{3}) (\d,|\d|\d{2},|\d{2}) \d{4}', output)
    if match_word:
        output = output.replace(match_word.group(), '')
    output = output.replace('\\', ' or ')
    speaker.speak(text=output, run=True)


def google_maps(query: str) -> bool:
    """Uses google's places api to get places nearby or any particular destination.

    This function is triggered when the words in user's statement doesn't match with any predefined functions.

    Args:
        query: Takes the voice recognized statement as argument.

    Returns:
        bool:
        Boolean True if Google's maps API is unable to fetch consumable results.
    """
    if not env.maps_api:
        return False

    maps_url = "https://maps.googleapis.com/maps/api/place/textsearch/json?"
    response = requests.get(maps_url + 'query=' + query + '&key=' + env.maps_api)
    collection = response.json()['results']
    required = []
    for element in range(len(collection)):
        try:
            name = collection[element]['name']
            rating = collection[element]['rating']
            full_address = collection[element]['formatted_address']
            geometry = collection[element]['geometry']['location']
            address = re.search('(.*)Rd|(.*)Ave|(.*)St |(.*)St,|(.*)Blvd|(.*)Ct', full_address)
            address = address.group().replace(',', '')
            new_dict = {"Name": name, "Rating": rating, "Address": address, "Location": geometry, "place": full_address}
            required.append(new_dict)
        except (AttributeError, KeyError):
            pass
    if required:
        required = sorted(required, key=lambda sort: sort['Rating'], reverse=True)
    else:
        return True
    results = len(required)
    speaker.speak(text=f"I found {results} results sir!") if results != 1 else None
    start = globals.current_location_['current_lat'], globals.current_location_['current_lon']
    n = 0
    for item in required:
        item['Address'] = item['Address'].replace(' N ', ' North ').replace(' S ', ' South ').replace(' E ', ' East ') \
            .replace(' W ', ' West ').replace(' Rd', ' Road').replace(' St', ' Street').replace(' Ave', ' Avenue') \
            .replace(' Blvd', ' Boulevard').replace(' Ct', ' Court')
        latitude, longitude = item['Location']['lat'], item['Location']['lng']
        end = f"{latitude},{longitude}"
        far = round(geodesic(start, end).miles)
        miles = f'{far} miles' if far > 1 else f'{far} mile'
        n += 1
        if results == 1:
            option = 'only option I found is'
            next_val = "Do you want to head there sir?"
        elif n <= 2:
            option = f'{inflect.engine().ordinal(n)} option is'
            next_val = "Do you want to head there sir?"
        elif n <= 5:
            option = 'next option would be'
            next_val = "Would you like to try that?"
        else:
            option = 'other'
            next_val = 'How about that?'
        speaker.speak(text=f"The {option}, {item['Name']}, with {item['Rating']} rating, "
                           f"on{''.join([j for j in item['Address'] if not j.isdigit()])}, which is approximately "
                           f"{miles} away. {next_val}", run=True)
        sys.stdout.write(f"\r{item['Name']} -- {item['Rating']} -- "
                         f"{''.join([j for j in item['Address'] if not j.isdigit()])}")
        converted = listener.listen(timeout=3, phrase_limit=3)
        if converted != 'SR_ERROR':
            if 'exit' in converted or 'quit' in converted or 'Xzibit' in converted:
                break
            elif any(word in converted.lower() for word in keywords.ok):
                maps_url = f'https://www.google.com/maps/dir/{start}/{end}/'
                webbrowser.open(url=maps_url)
                speaker.speak(text="Directions on your screen sir!")
                return False
            elif results == 1:
                return False
            elif n == results:
                speaker.speak(text="I've run out of options sir!")
                return False
            else:
                continue
        else:
            return False
