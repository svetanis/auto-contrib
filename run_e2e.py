import sys
import os

# Zero-dependency .env loader
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value.strip('"\'')

# Ensure the app module can be found
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.agent import root_agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

def main():
    prompt = "Please fix the add() method in the Calculator class so it adds instead of subtracts. The repository is located locally at: ../auto-contrib-sandbox"
    print("--- Starting auto-contrib End-to-End Test ---")
    print(f"Instruction: {prompt}\n")
    
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="local_user", app_name="auto-contrib")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="auto-contrib")
    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    
    print("Agent Response:")
    for event in runner.run(new_message=message, user_id="local_user", session_id=session.id):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text, end="", flush=True)
                elif part.function_call:
                    print(f"\n[Agent] Calling tool: {part.function_call.name}({part.function_call.args})")
                elif part.function_response:
                    print(f"\n[Tool Output] {part.function_response.name}: {part.function_response.response}")
    print("\n\n--- Test Complete ---")

if __name__ == "__main__":
    main()
