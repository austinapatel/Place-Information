# Places Amazon Alexa skill developed by Austin Patel

# TODO: handle case in which user just says query without 'nearby'

from urllib.request import Request, urlopen
from urllib.error import HTTPError
from json import loads

# Decrypt code should run once and variables stored outside of the function
# handler so that these are decrypted once per container
# TODO: Fix encryption
from base64 import b64decode
import boto3
import os

# TODO: remove key

# PLACES_API_KEY = boto3.client('kms').decrypt(CiphertextBlob=b64decode(os.environ['places_api_key']))['Plaintext']
# GEOCODING_API_KEY = boto3.client('kms').decrypt(CiphertextBlob=b64decode(os.environ['geocoding_api_key']))['Plaintext']
PLACES_API_KEY, GEOCODING_API_KEY = os.environ['places_api_key'], os.environ['geocoding_api_key']

# Variables
START_QUESTION = 'What would you like to search for nearby?'
HELP_QUESTION = START_QUESTION
NO_QUESTION = ''

HELP_SPEECH = 'This skil will tell you what places are nearby.  Make sure you have a location entered in the Alexa app and allow the location permission.  For example, you could say nearby pizza.  Make sure to say nearby when using this skill.'
UNEXPECTED_ANSWER_SPEECH = 'I was not expecting you to say that right now.'
WELCOME_SPEECH = 'You can ask this skill for nearby places.  For example you can say nearby pizza.'
REQUEST_PERMISSION_SPEECH = 'This Alexa skill does not have permission to access your location, which ' \
                            'is required for this skill to function.  Please go to the Alexa app to enable the ' \
                            'location permission.'
NO_ADDRESS_AVAILABLE_SPEECH = 'You have granted this skill permission to access your location, however ' \
                              'you have not entered a location in the alexa app.  In the settings of the Alexa ' \
                              'app select your Alexa enabled device and add a street address.'
BAD_RESPONSE_CODE_SPEECH = 'This skill was unable to receive data correctly from Google or Amazon '
NEARBY_SPEECH = 'Places close to you are '
NO_PLACES_FOUND_SPEECH = 'No places were found for the query '
NO_SLOT_GIVEN_SPEECH = 'Please include a search query in your request.'

START_INTENT, NEARBY_INTENT = 'Start', 'Nearby'

HELP_INTENT, CANCEL_INTENT, STOP_INTENT = 'AMAZON.HelpIntent', 'AMAZON.CancelIntent', 'AMAZON.StopIntent'
LAUNCH_REQUEST, INTENT_REQUEST, SESSION_ENDED_REQUEST = 'LaunchRequest', 'IntentRequest', 'SessionEndedRequest'

ADDRESS_PERMISSION = 'read::alexa:device:all:address'

FOOD_TYPE_SLOT_NAME = 'FoodType'

OK_STATUS_CODE = 'OK'
ZERO_RESULTS_STATUS_CODE = 'ZERO_RESULTS'
OVER_QUERY_LIMIT_STATUS_CODE = 'OVER_QUERY_LIMIT'
REQUEST_DENIED_STATUS_CODE = 'REQUEST_DENIED'
INVALID_REQUEST_STATUS_CODE = 'INVALID_REQUEST'

NEARBY_PLACE_LIMIT = 5

lat, lng = None, None
event = None
last_question = NO_QUESTION


# Initialization
def on_session_start():
    """ Initializes session """


# Permissions
def request_permission(name, speech_request_response):
    speech_request_response['response']['card'] = {
        "type": "AskForPermissionsConsent",
        "permissions": [
            name
        ]
    }

    return speech_request_response


# Alexa helpers
def get_slot(slot_name):
    """ Finds a value in a given slot """
    return event['request']['intent']['slots'][slot_name]['value']


# Speech
def say(output='', reprompt_text='', title='', should_end_session=True):
    """ Builds a spoken response and will end the session by default """
    output = str(output)
    if reprompt_text == '':
        reprompt_text = output

    return {
        'version': '1.0',
        'sessionAttributes': {},
        'response': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': output
            },
            'reprompt': {
                'outputSpeech': {
                    'type': 'PlainText',
                    'text': reprompt_text
                }
            },
            'shouldEndSession': should_end_session
        }
    }


def question(question_base, extension='', intro=''):
    """ Asks a question and prepares the users response """
    if extension != '':
        extension = ' ' + str(extension)

    question_text = question_base + extension + '?'

    return say(output=intro + ' ' + question_text, reprompt_text=question_text, should_end_session=False)


def welcome():
    """ Welcomes the user with a message and randomly picks a question to ask the user about their number """
    on_session_start()
    return question(START_QUESTION, intro=WELCOME_SPEECH)


def help():
    """ Provides the user with help based on where they are in the program """
    return question(HELP_QUESTION, intro=HELP_SPEECH)

def end():
    """ Terminates the current session """
    return say()


def get_missing_slot():
    """ Support for dialog directives """
    return {
        "response": {
            "directives": [
                {
                    "type": "Dialog.Delegate"
                }
            ],
            "shouldEndSession": False
        },
        "sessionAttributes": {}
    }


# Program specific logic
def question_answer(response):
    """ Handles the users response to a given question and the scenario in which this
    intent is called even though there was no question given

    Parameters:
        response: a string that is the name of an intent
    """
    return say(UNEXPECTED_ANSWER_SPEECH)


def location_manager():
    """ Send permission card to user if they have not given permission to use location """
    if 'permissions' not in event['context']['System']['user']:
        event['context']['System']['user']['permissions'] = {}
    if 'consentToken' not in event['context']['System']['user']['permissions']:
        return request_permission(ADDRESS_PERMISSION, say(REQUEST_PERMISSION_SPEECH, should_end_session=True))

    try:
        address = get_address()
    except HTTPError as e:
        return say(BAD_RESPONSE_CODE_SPEECH + str(e))

    if not address:
        return say(NO_ADDRESS_AVAILABLE_SPEECH)

    try:
        global lat, lng
        lat, lng = get_lat_long(address)
    except HTTPError as e:
        return say(BAD_RESPONSE_CODE_SPEECH + str(e))

    # don't return anything if program successfully got location


# TODO: Handle all response codes
def get_address():
    """ Returns the users address pulled from amazon servers, returns None
    if user has not entered address into the Alexa app and raises an error if
    the response from the server had a bad reponse code. """

    # get user tokens
    consent_token = event['context']['System']['user']['permissions']['consentToken']
    device_id = event['context']['System']['device']['deviceId']
    url = 'https://api.amazonalexa.com/v1/devices/{}/settings/address'.format(device_id)

    # query api
    request = Request(url)
    request.add_header('Authorization', 'Bearer ' + consent_token)
    opened = urlopen(request)

    if opened.getcode() != 200: # Bad response code
        raise HTTPError(opened.getcode())

    response = loads(opened.read())

    if not response['addressLine1']: # Address not entered
        return None

    return ', '.join([response['addressLine1'], response['city'], response['stateOrRegion']])


# TODO: Handle all response codes
def get_lat_long(address):
    """ Convert address into latitude and longitude """
    address = address.replace(' ', '+')

    url = 'https://maps.googleapis.com/maps/api/geocode/json?address={}&key={}'.format(address, GEOCODING_API_KEY)
    response = loads(urlopen(Request(url)).read())

    if response['status'] != OK_STATUS_CODE:
        raise HTTPError(response['status'])

    location = response['results'][0]['geometry']['location']

    return location['lat'], location['lng']


# TODO: handle all response codes
def get_nearby_places(query):
    """ Uses latitude and longitude to get nearby places based on a query """
    query = query.replace(' ', '+')
    url = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={},{}&radius=10000&keyword={}&key={}'.format(lat, lng, query, PLACES_API_KEY)

    response = loads(urlopen(Request(url)).read())

    if response['status'] != OK_STATUS_CODE and response['status'] != ZERO_RESULTS_STATUS_CODE:
        raise HTTPError(response['status'])

    # Return the unique names of nearby places
    return list(set([place['name'] for place in response['results']]))


def nearby_information():
    """ Handles intent for when user asks 'nearby ...' such as 'nearby pizza'
    by saying information about nearby places """
    try:
        slot_value = get_slot(FOOD_TYPE_SLOT_NAME)

        places = get_nearby_places(slot_value)
    except HTTPError as e:
        return say(BAD_RESPONSE_CODE_SPEECH + str(e))
    except KeyError:
        return say(NO_SLOT_GIVEN_SPEECH)

    if len(places) == 0:
        return say(NO_PLACES_FOUND_SPEECH + get_slot(FOOD_TYPE_SLOT_NAME))

    result = ''
    for place in places[:NEARBY_PLACE_LIMIT]:
        result += place + ', '

    return say(NEARBY_SPEECH + result)


# Event handlers and related variables
def handle_intent():
    """ Called when the user specifies an intent for this skill """
    intent_name = event['request']['intent']['name']

    # Handle partially completed intent
    if (event['request']['dialogState'] == 'STARTED' or event['request']['dialogState'] == 'IN_PROGRESS'):
        return get_missing_slot()

    if intent_name in name_to_handler:
        return name_to_handler[intent_name]()
    else:
        return question_answer(intent_name)


def lambda_handler(event_dict, context):
    """ Route the incoming request based on type (LaunchRequest, IntentRequest,
    etc.) The JSON body of the request is provided in the event parameter.
    """
    global event
    event = event_dict

    # Let the location getting process override behavior
    location_response = location_manager()
    if location_response != None:
        return location_response

    if event['session']['new']:
        on_session_start()

    print(event)

    return request_to_handler[event['request']['type']]()


name_to_handler = {HELP_INTENT: help,
                   CANCEL_INTENT: end,
                   STOP_INTENT: end,
                   START_INTENT: welcome,
                   NEARBY_INTENT: nearby_information}

request_to_handler = {LAUNCH_REQUEST: welcome,
                      INTENT_REQUEST: handle_intent,
                      SESSION_ENDED_REQUEST: end}
