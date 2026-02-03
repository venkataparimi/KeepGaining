import asyncio
import os
import openai
import traceback
from dotenv import load_dotenv

# Load .env
load_dotenv('c:/sources/KeepGaining/.env')

async def main():
    print("Testing OpenAI SDK directly...")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found in .env")
        return

    print(f"Client initialized with key: {api_key[:5]}...")
    
    try:
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello"}
            ]
        )
        print("\nSUCCESS! Response:")
        print(response.choices[0].message.content)
        
    except openai.APIConnectionError as e:
        print("\nFAILURE! APIConnectionError caught.")
        print(f"Message: {e}")
        print(f"Cause: {e.__cause__}")
        traceback.print_exc()
    except Exception as e:
        print(f"\nFAILURE! Unexpected error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
