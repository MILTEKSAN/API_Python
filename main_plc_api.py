import time
from mil_api import Client, ApiError, ConnectionError, SendError

# --- Configuration ---
# Replace with the actual IP address and port of your CNC/PLC server
HOST = "192.168.1.254"  # Example IP address 
PORT = 60000

GLOBAL_MOTOR_ENABLE_SET_ADDRESS = 0 # SET ADDRESS
GLOBAL_MOTOR_ENABLE_GET_ADDRESS = 1 # GET ADDRESS

# LEFT_JOG_FORWARD_MOTOR_ADDRESS = 1
# LEFT_JOG_BACKWARD_MOTOR_ADDRESS = 2
# RIGHT_JOG_FORWARD_MOTOR_ADDRESS = 3
# RIGHT_JOG_BACKWARD_MOTOR_ADDRESS = 4

# LEFT_SPEED_ADDRESS = 0
# RIGHT_SPEED_ADDRESS = 1

# LEFT_STEERING_MOTOR_ADDRESS = 2
# RIGHT_STEERING_MOTOR_ADDRESS = 3

def main():
    global client
    client = Client()
    client.connect(HOST, PORT, timeout=5)
    print("Connected to the server.")
    time.sleep(1.0)

    if client.is_connected():
        flag, cntr = True, 0
    while True:
        if client.is_connected() and client.get_bool_value(GLOBAL_MOTOR_ENABLE_GET_ADDRESS):
            pass
        else:
            print(client.get_bool_value(GLOBAL_MOTOR_ENABLE_GET_ADDRESS))
            
            input("Press Enter to continue...")
            if not client.is_connected():
                client.connect(HOST, PORT, timeout=3)
                print("Connected to the server.")
            if not client.get_bool_value(GLOBAL_MOTOR_ENABLE_GET_ADDRESS):
                client.set_plc_bool(GLOBAL_MOTOR_ENABLE_SET_ADDRESS, True)
                print("Motors enabled successfully")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down motors...")
        client.set_plc_bool(GLOBAL_MOTOR_ENABLE_SET_ADDRESS, False)
        print("Motors disabled successfully")
        time.sleep(0.5)
        client.disconnect()
    except Exception as e:
        client.set_plc_bool(GLOBAL_MOTOR_ENABLE_SET_ADDRESS, False)
        print("Motors disabled successfully")
        print(f"An error occurred: {e}")
        time.sleep(0.5)
        client.disconnect()
        raise e