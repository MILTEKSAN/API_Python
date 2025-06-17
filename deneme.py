import time
# Import the client and its specific exceptions from your API file
from mil_api import Client, ApiError, ConnectionError, SendError

# --- Configuration ---
# Replace with the actual IP address and port of your CNC/PLC server
HOST = "192.168.1.254"  # Example IP address 
PORT = 60000

# The PLC memory address we will write to and read from
TEST_ADDRESS = 150

def run_api_demonstration():
    """
    A minimal, self-contained example of the mil_api.Client workflow.
    """
    print("--- Starting MilConnAPI Demonstration ---")
    print(f"Attempting to connect to server at {HOST}:{PORT}...")

    # Using a 'with' statement is the best practice. It automatically
    # handles calling client.disconnect() when the block is exited,
    # even if errors occur.
    try:
        with Client() as client:
            # 1. CONNECT
            # This establishes the connection and starts the background
            # message-processing thread required for getting updates.
            client.connect(HOST, PORT, timeout=5)
            print("✅ Successfully connected to the server.")

            # 2. WRITE A VALUE
            # We will send a floating-point value to a DWORD address.
            # The API automatically reinterprets the float's bits as a 32-bit integer.
            value_to_send = 123.456
            print(f"\nSTEP 1: Writing float '{value_to_send}' to address {TEST_ADDRESS}...")
            client.set_plc_dword(TEST_ADDRESS, value_to_send)
            print(" -> Write command sent successfully.")

            # 3. REQUEST THE VALUE
            # This tells the server: "Please send me the current value at this address."
            # The response will be processed by the client's background thread.
            print(f"\nSTEP 2: Requesting value from address {TEST_ADDRESS}...")
            client.request_plc_value(TEST_ADDRESS, "DWORD")
            print(" -> Request command sent successfully.")

            # 4. WAIT FOR THE RESPONSE
            # We must wait for the network round-trip and for the background
            # thread to process the incoming message from the server.
            print("\nSTEP 3: Waiting 1 second for the server to respond...")
            time.sleep(1)

            # 5. GET THE VALUE
            # This retrieves the value from the client's local data cache, which was
            # updated by the background thread. It does NOT send a new network request.
            print("\nSTEP 4: Reading the value from the client's local memory...")
            retrieved_dword = client.get_dword_value(TEST_ADDRESS)
            print(f"✅ Retrieved DWORD from address {TEST_ADDRESS}: {retrieved_dword}")
            print("(Note: The value is an integer because it's the raw 32-bit data from the PLC)")

    except (ConnectionError, SendError, ApiError) as e:
        print(f"\n❌ An API error occurred: {e}")
    except FileNotFoundError:
        print("\n❌ CRITICAL ERROR: The library file (milconnapi.dll or .so) was not found.")
        print("   Please ensure it is in the same directory as this script.")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")
    finally:
        # The 'with' statement ensures disconnection happens here automatically.
        print("\n--- Demonstration Finished ---")


if __name__ == "__main__":
    run_api_demonstration()