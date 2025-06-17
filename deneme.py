import time
import sys

# --- Import your custom module ---
try:
    import mil_api as api
except (OSError, AttributeError) as e:
    print(f"FATAL: Could not load the mil_api module. Error: {e}")
    print("Ensure milconnapi.dll (or .so) is in the same directory.")
    sys.exit(1) # Exit the script if the library fails to load

# --- Configuration ---
HOST = "192.168.1.254"
PORT = 60000
ADDRESSES_TO_MONITOR = [0, 1, 2]

def run_monitor():
    """Connects to the server and polls DWORD values in a loop."""
    client = None
    try:
        # 1. Create a client and connect to the server
        print("--> Attempting to connect...")
        client = api.create_client()
        if not api.connect(client, HOST, PORT):
            print(f"❌ Connection failed to {HOST}:{PORT}.")
            return

        print(f"✅ Connected successfully. Monitoring addresses: {ADDRESSES_TO_MONITOR}")
        print("--> Press Ctrl+C to stop.\n")

        # 2. Start the main monitoring loop
        while True:
            # try:
                # Read each address and store the results
                results = []
                for address in ADDRESSES_TO_MONITOR:
                    value = api.request_dword(client, address)
                    results.append(f"Addr[{address}]: {value}")

                # Print the results on a single, updating line
                # The '\r' character moves the cursor to the beginning of the line
                # The 'end=""' prevents adding a newline character
                print(" | ".join(results) + "   ", end="\r")

                # Wait for one second before the next poll
                time.sleep(1)

            # except (api.ConnectionError, api.ReceiveError, TypeError, ValueError) as e:
            #     print(f"\n❌ A communication error occurred: {e}")
            #     print("--> Halting monitor.")
            #     break # Exit the loop on any API error

    except KeyboardInterrupt:
        # This block runs when the user presses Ctrl+C
        print("\n--> User stopped the monitor. Exiting gracefully.")

    finally:
        # 3. This block always runs to ensure the client is destroyed
        if client:
            print("--> Disconnecting client.")
            api.destroy_client(client)
        print("--> Script finished.")

# --- Main Execution Block ---
if __name__ == "__main__":
    run_monitor()