import ctypes
import platform
import time
import struct

# ───────────── Load the shared library ─────────────
if platform.system() == 'Windows':
    libname = "milconnapi.dll"
else:
    libname = "./libmilconnapi.so"

mil = ctypes.CDLL(libname)

# ───────────── Define function signatures ─────────────
mil.create_client.restype = ctypes.c_void_p
mil.destroy_client.argtypes = [ctypes.c_void_p]
mil.connect_to_server.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
mil.connect_to_server.restype = ctypes.c_bool
mil.get_message_type.argtypes = [ctypes.c_char_p]
mil.get_message_type.restype = ctypes.c_int
mil.send_message.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
mil.send_message.restype = ctypes.c_bool
mil.receive_message.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p, ctypes.c_int]
mil.receive_message.restype = ctypes.c_int

# ───────────── Connect to Server ─────────────
client = mil.create_client()
host = b"127.0.0.1"
port = 60000

print("🚀 Connecting to server...")

if mil.connect_to_server(client, host, port):
    print("✅ Connected to server.")


    try:
        while True:
            msg_type = mil.get_message_type(b"UserDefinedDWord")

            # Data to send
            address = 100            # uint16_t
            value = 12345678         # uint32_t

            # Pack payload: little-endian '<' + H (2-byte) + I (4-byte)
            payload = struct.pack('<HI', address, value)

            # Send the message
            mil.send_message(client, msg_type, payload, len(payload))
            print(f"✅ Sent UserDefinedDWord to address {address} with value {value}")

            time.sleep(1)

    except KeyboardInterrupt:
        print("⛔ Interrupted by user")

else:
    print("❌ Connection failed")

mil.destroy_client(client)
print("🗑️ Client destroyed")