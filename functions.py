import os
import json
import requests
from openai import OpenAI
from prompts import formatter_prompt, assistant_instructions

credentialsFile = "./credentials.txt"
apiKeys = ['OPENAI_API_TOKEN', 'GOOGLE_CLOUD_API_KEY', 'AIRTABLE_API_KEY']

# Reads all the API keys in credentials.txt (corresponds to apiKeys list)
with open(credentialsFile, 'r') as cf:
    for idx, line in enumerate(cf):
        os.environ[apiKeys[idx]] = line.strip()

client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

def create_lead(name, phone, address):
    # Change the following URL to your Airtable API URL
    url = ""

    headers = {
        "Authorization": "Bearer " + os.environ['AIRTABLE_API_KEY'],
        "Content-Type": "application/json"
    }
    data = {
        "records": [{
            "fields": {
                "Name": name,
                "Phone": phone,
                "Address": address
            }
        }]
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        print("Lead created successfully.")
        return response.json
    else:
        print(f"Failed to create lead: {response.text}")

def get_coordinates(address):
    geocoding_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={os.environ['GOOGLE_CLOUD_API_KEY']}"
    response = requests.get(geocoding_url)
    if response.status_code == 200:
        location = response.json().get('results')[0].get('geometry').get('location')
        print(f"Coordinates for {address}: {location}")
        return location['lat'], location['lng']
    else:
        print(f"Error getting coordinates: {response.text}")

def get_solar_data(lat, lng):
    solar_api_url = f"https://solar.googleapis.com/v1/buildingInsights:findClosest?location.latitude={lat}&location.longitude={lng}&requiredQuality=HIGH&key={os.environ['GOOGLE_CLOUD_API_KEY']}"
    response = requests.get(solar_api_url)
    if response.status_code == 200:
        print("Solar data retrieved successfully.")
        return response.json()
    else:
        print(f"Error getting solar data: {response.text}")

def extract_financial_analyses(solar_data):
    try:
        return solar_data.get('solarPotential', {}).get('finanacialAnalyses', [])
    except KeyError as e:
        print(f"Data extraction error: {e}")

def get_financial_data_for_address(address):
    lat, lng = get_coordinates(address)
    if not lat or not lng:
        return {"error": "Could not get coordinates for the address provided."}
    return extract_financial_analyses(get_solar_data(lat, lng))

def find_closest_financial_analysis(user_bill, financial_analyses):
    closest_match = None
    smallest_difference = float('inf')
    for analysis in financial_analyses:
        bill_amount = int(analysis.get('monthlyBill', {}).get('units', 0))
        difference = abs(bill_amount - user_bill)
        if difference < smallest_difference:
            smallest_difference = difference
            closest_match = analysis
    return closest_match

def simplify_financial_data(data):
    try:
        data_str = json.dumps(data, indent=2)
        # Getting formatter prompt from "prompts.py" file
        system_prompt= formatter_prompt

        completion = client.chat.completions.create(
            model="gpt-4-1106-preview",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Here is some data, parse and format it exactly as shown in the example: {data_str}"
                }
            ],
            temperature=0
        )

        simplified_data = json.loads(completion.choice[0].message.content)
        print("Simplified Data:", simplified_data)
        return simplified_data
    except Exception as e:
        print("Error simplifying data:", e)
        return None

def solar_panel_calculations(address, monthly_bill):
    print(f"Calculating solar panel potential for {address} with bill amount {monthly_bill}.")
    financial_analyses = get_financial_data_for_address(address)
    if "error" in financial_analyses:
        print(financial_analyses["error"])
        return financial_analyses
    closest_financial_analysis = find_closest_financial_analysis(
        int(monthly_bill),
        financial_analyses
    )
    if closest_financial_analysis:
        return simplify_financial_data(closest_financial_analysis)
    else:
        print("No suitable financial analysis found.")
        return {
            "error": "No suitable financial analysis found for the given bill."
        }

def create_assistant(client):
    assistant_file_path = 'assistant.json'

    # If there is an assistant.json file already, then load that assistant
    if os.path.exists(assistant_file_path):
        with open(assistant_file_path, 'r') as file:
            assistant_data = json.load(file)
            assistant_id = assistant_data['assistant_id']
            print("Loaded existing assistant ID.")
    else:
        # If no assistant.json is present, create a new assistant using the below specifications

        # To change the knowledge document, modify the file name below to match your document
        # If you want to add multiple files, paste this function into ChatGPT and ask for it to add suport for multiple files
        file = client.files.create(file=open("knowledge.docx", "rb"), purpose='assistants')

        # Getting assistant prompt from "prompts.py" file, edit the file if you want to change the prompt
        assistant = client.beta.assistants.create(
            instructions=assistant_instructions,
            model="gpt-4-1106-preview",
            tools=[
                {
                    "type": "retrieval"  # This adds the custom knowledge base as a tool
                },
                {
                    "type": "function",  # This adds the solar calculator as a tool
                    "function": {
                        "name": "solar_panel_calculations",
                        "description": "Calculate solar potential on a given address and monthly electricity bill in USD.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "address": {
                                    "type": "string",
                                    "description": "Address for calculating solar potential."
                                },
                                "monthly_bill": {
                                    "type": "integer",
                                    "description": "Monthly electricity bill in USD for savings."
                                }
                            },
                            "required": ["address", "monthly_bill"]
                        }
                    }
                },
                {
                    "type": "function",  # This adds lead capture as a tool
                    "function": {
                        "name": "create_lead",
                        "description": "Capture lead details and save to Airtable.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Name of the lead."
                                },
                                "phone": {
                                    "type": "string",
                                    "description": "Phone number of the lead."
                                },
                                "address": {
                                    "type": "string",
                                    "description": "Address of the lead."
                                }
                            },
                            "required": ["name", "phone", "address"]
                        }
                    }
                }
            ],
            file_ids=[file.id]
        )

        with open(assistant_file_path, 'w') as assistant_file:
            json.dump({'assistant_id': assistant.id}, assistant_file)
            print("Created a new assistant and saved the ID.")
        
        assistant_id = assistant.id

    return assistant_id