import os
import json
import time
from flask import Flask, request, jsonify
import openai
from openai import OpenAI
import functions
from packaging import version


# Credentials file should have 3 lines -- 1st is OPENAI API key, 2nd is GCP Maps Platform API key, 3rd is Airtable API key
# No extra whitespaces in that file
credentialsFile = "./credentials.txt"
apiKeys = ['OPENAI_API_TOKEN', 'GOOGLE_CLOUD_API_KEY', 'AIRTABLE_API_KEY']

# Reads all the API keys in credentials.txt (corresponds to apiKeys list)
with open(credentialsFile, 'r') as cf:
    for idx, line in enumerate(cf):
        os.environ[apiKeys[idx]] = line.strip()

requiredVersion = version.parse("1.1.1")
currentVersion = version.parse(openai.__version__)

if currentVersion < requiredVersion:
    raise ValueError(f"Error: OpenAI version {openai.__version__} is less than the required version 1.1.1")
else:
    print("OpenAI version is compatible.")

app = Flask(__name__)

client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

# Call create_assistant function from functions.py
assistant_id = functions.create_assistant(client)

# Start conversation thread
@app.route('/start', methods=['GET'])
def startConversation():
    print("Starting a new conversation..")
    thread = client.beta.threads.create()
    print(f"New thread created with ID: {thread.id}")
    return jsonify({"thread_id": thread.id})

# Generate response
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    thread_id = data.get('thread_id')
    user_input = data.get('message', '')

    if not thread_id:
        print("Error: Missing thread_id")
        return jsonify({"error": "Missing thread_id"}), 400
    print(f"Received message: {user_input} for thread ID: {thread_id}")

    # Add the user's message to the thread
    client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_input)

    # Run the assistant
    run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)

    # Check if the run requires action/tool (function call)
    while True:
        run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        print(f"Run status: {run_status.status}")
        if run_status.status == 'completed':
            break
        elif run_status.status == 'requires_action':
            for tool_call in run_status.required_action.submit_tool_outputs.tool_calls:
                if tool_call.function.name == "solar_panel_calculations":
                    # Process solar panel calculations
                    arguments = json.loads(tool_call.function.arguments)
                    output = functions.solar_panel_calculations(
                        arguments["addresss"], 
                        arguments["monthly_bill"]
                    )
                    client.beta.threads.runs.submit_tool_outputs(
                        thread_id=thread_id, 
                        run_id=run.id,
                        tool_outputs=[{"tool_call_id": tool_call.id, "output": json.dumps(output)}]
                    )
                elif tool_call.function.name == "create_lead":
                    # Process lead creation
                    arguments = json.loads(tool_call.function.arguments)
                    output = functions.create_lead(arguments["name"], arguments["phone"], arguments["address"])
                    client.beta.threads.runs.submit_tool_outputs(
                        thread_id=thread_id,
                        run_id=run.id,
                        tool_outputs=[{"tool_call_id": tool_call.id, "output": json.dumps(output)}]
                    )
            # Wait for a second before checking again
            time.sleep(1)
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    response = messages.data[0].content[0].text.value

    print(f"Assistant response: {response}")
    return jsonify({"response": response})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
        

                






