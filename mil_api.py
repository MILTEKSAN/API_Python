# ...existing code...
import ctypes
import platform
import threading
import time
# import json # No longer needed
import struct # Added for float/double reinterpretation
from typing import Optional, Union # Union for type hints
import os

# --- API Configuration ---
# Update this with the actual name of your compiled library
LIB_NAME = "milconnapi.dll" if platform.system() == "Windows" else "libmilconnapi.so"

class ApiError(Exception):
    """Base exception for API errors."""
    pass

class ConnectionError(ApiError):
    """Raised for connection-related failures."""
    pass

class SendError(Exception):
    """Raised when a message send operation fails."""
    pass

# --- CTYPES STRUCTURES ---
# These classes must exactly mirror the C++ structs in CNCMessageStructs.h




# This class loads the DLL and defines the function signatures.
class _C_API:
    def __init__(self, lib_path: str):
        try:
            self.lib = ctypes.CDLL(lib_path)
        except OSError as e:
            raise ApiError(f"Failed to load library at '{lib_path}'. "
                           f"Ensure the library exists and all dependencies are available. Error: {e}")
        self._define_signatures()

    def _define_signatures(self):
        # --- Lifecycle ---
        self.lib.create_client.restype = ctypes.c_void_p
        self.lib.destroy_client.argtypes = [ctypes.c_void_p]

        # --- Connection ---
        self.lib.connect_to_server.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self.lib.connect_to_server.restype = ctypes.c_bool
        self.lib.disconnect_from_server.argtypes = [ctypes.c_void_p]
        self.lib.is_connected.argtypes = [ctypes.c_void_p]
        self.lib.is_connected.restype = ctypes.c_bool

        # --- Message Processing ---
        self.lib.process_messages.argtypes = [ctypes.c_void_p]


        # --- Data Getters ---

        # self.lib.get_io_status.argtypes = [ctypes.c_void_p, ctypes.POINTER(IOStatus)]
        
        self.lib.get_bool_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_bool)]
        self.lib.get_bool_value.restype = ctypes.c_bool
        self.lib.get_byte_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8)]
        self.lib.get_byte_value.restype = ctypes.c_bool
        self.lib.get_word_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint16)]
        self.lib.get_word_value.restype = ctypes.c_bool
        self.lib.get_dword_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
        self.lib.get_dword_value.restype = ctypes.c_bool
        self.lib.get_lword_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint64)]
        self.lib.get_lword_value.restype = ctypes.c_bool
        
        # --- Data Setters (for UserDefined... messages) ---
        self.lib.set_bool_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_bool]
        self.lib.set_bool_value.restype = ctypes.c_bool
        
        self.lib.set_byte_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint8]
        self.lib.set_byte_value.restype = ctypes.c_bool
        
        self.lib.set_word_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint16]
        self.lib.set_word_value.restype = ctypes.c_bool
        
        self.lib.set_dword_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]
        self.lib.set_dword_value.restype = ctypes.c_bool
        
        self.lib.set_lword_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint64]
        self.lib.set_lword_value.restype = ctypes.c_bool
        
        self.BoolCameFromServer = ctypes.c_bool.in_dll(self.lib, "BoolCameFromServer")
        self.ByteCameFromServer = ctypes.c_bool.in_dll(self.lib, "ByteCameFromServer")
        self.WordCameFromServer = ctypes.c_bool.in_dll(self.lib, "WordCameFromServer")
        self.DWordCameFromServer = ctypes.c_bool.in_dll(self.lib, "DWordCameFromServer")
        self.LWordCameFromServer = ctypes.c_bool.in_dll(self.lib, "LWordCameFromServer")
# --- Main Python Client Class ---
class Client:
    """
    A Python client for the MILTEKSAN CNC v2 API.
    This client operates asynchronously, using a background thread
    to process incoming messages from the server.
    """
    def __init__(self, lib_path: str = LIB_NAME):
        # Try to find the library relative to this script file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Check if lib_path is absolute, if not, join with script_dir
        if not os.path.isabs(lib_path):
            lib_path = os.path.join(script_dir, lib_path)
            
        self._api = _C_API(lib_path)
        self.client_handle = self._api.lib.create_client()
        if not self.client_handle:
            raise ApiError("Failed to create client instance from library.")
        
        self._is_connected_flag = False # Internal flag, distinct from C is_connected
        self._processing_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock() # Protects client_handle and _is_connected_flag
        print("INFO: Client instance created.")


    def connect(self, host: str, port: int, timeout: int = 5):
        """
        Initiates a connection to the server and starts a background
        thread to process messages.
        """
        if self._is_connected_flag:
            print("WARN: Already connected.")
            return

        with self._lock:
            if self._is_connected_flag: # Double check after acquiring lock
                print("WARN: Already connected (race condition avoided).")
                return

            # The C++ function starts the connection attempt
            # connect_to_server itself might be asynchronous in C++
            self._api.lib.connect_to_server(self.client_handle, host.encode('utf-8'), port)

            # Start the background message processor
            self._stop_event.clear()
            self._processing_thread = threading.Thread(target=self._message_processor)
            self._processing_thread.daemon = True # Allow program to exit even if thread is running
            self._processing_thread.start()

            # Wait for the connection to be confirmed by is_connected
            start_time = time.time()
            while not self._api.lib.is_connected(self.client_handle):
                if time.time() - start_time > timeout:
                    print(f"ERROR: Connection to {host}:{port} timed out after {timeout} seconds.")
                    self._stop_event.set()
                    if self._processing_thread and self._processing_thread.is_alive():
                        self._processing_thread.join(timeout=1.0)
                    # No destroy_client here as disconnect() handles it.
                    # We don't call full disconnect as client_handle might be in a weird state.
                    raise ConnectionError(f"Connection to {host}:{port} timed out after {timeout} seconds.")
                if self._stop_event.is_set(): # If disconnect called from another thread
                    raise ConnectionError("Connection attempt aborted.")
                time.sleep(0.1)
            
            self._is_connected_flag = True
            print(f"INFO: Successfully connected to {host}:{port} and message processor started.")


    def _message_processor(self):
        """Target for the background thread. Continuously polls the C++ library."""
        print("INFO: Message processing thread started.")
        while not self._stop_event.is_set():
            if self.client_handle:
                self._api.lib.process_messages(self.client_handle)
            time.sleep(0.01) # 10ms loop, adjust as needed
        print("INFO: Message processing thread stopped.")

    def disconnect(self):
        """Disconnects from the server and cleans up resources."""
        if not self.client_handle:
            return

        print("INFO: Disconnecting...")
        self._stop_event.set() # Signal thread to stop
        if self._processing_thread and self._processing_thread.is_alive():
            self._processing_thread.join(timeout=2.0) # Wait for thread to finish

        with self._lock:
            if not self.client_handle: return # Check again in case of race condition
            self._api.lib.disconnect_from_server(self.client_handle)
            self._api.lib.destroy_client(self.client_handle)
            self.client_handle = None
            self._is_connected = False
        
        print("INFO: Client disconnected and destroyed.")
        
    def is_connected(self) -> bool:
        """Checks if the client believes it is connected."""
        # Check both Python flag and C-layer, prioritizing Python flag if recently disconnected
        with self._lock:
            if not self.client_handle or not self._is_connected_flag:
                return False
            # If Python flag is true, re-verify with C-layer
            self._is_connected_flag = self._api.lib.is_connected(self.client_handle)
            return self._is_connected_flag
    
    def set_bool_value(self, address: int, value: bool):
        """Sets a boolean value in the PLC's shared memory via UserDefinedBool message."""
        if not self.is_connected(): raise ConnectionError("Not connected.")
        if not isinstance(value, bool): raise TypeError("Value must be a boolean.")
        
        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")
            success = self._api.lib.set_bool_value(self.client_handle, ctypes.c_uint32(address), ctypes.c_bool(value))
        if not success:
            if not self._api.lib.is_connected(self.client_handle): self._is_connected_flag = False
            raise SendError(f"Failed to set boolean value at address {address}.")
        print(f"INFO: set_bool_value(address={address}, value={value}) sent.")

    def set_byte_value(self, address: int, value: int):
        """Sets a byte value (0-255) in the PLC's shared memory."""
        if not self.is_connected(): raise ConnectionError("Not connected.")
        if not (0 <= value <= 255): raise ValueError("Byte value must be between 0 and 255.")

        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")
            success = self._api.lib.set_byte_value(self.client_handle, ctypes.c_uint32(address), ctypes.c_uint8(value))
        if not success:
            if not self._api.lib.is_connected(self.client_handle): self._is_connected_flag = False
            raise SendError(f"Failed to set byte value at address {address}.")
        print(f"INFO: set_byte_value(address={address}, value={value}) sent.")

    def set_word_value(self, address: int, value: int):
        """Sets a word value (0-65535) in the PLC's shared memory."""
        if not self.is_connected(): raise ConnectionError("Not connected.")
        if not (0 <= value <= 65535): raise ValueError("Word value must be between 0 and 65535.")
        
        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")
            success = self._api.lib.set_word_value(self.client_handle, ctypes.c_uint32(address), ctypes.c_uint16(value))
        if not success:
            if not self._api.lib.is_connected(self.client_handle): self._is_connected_flag = False
            raise SendError(f"Failed to set word value at address {address}.")
        print(f"INFO: set_word_value(address={address}, value={value}) sent.")

    def set_dword_value(self, address: int, value: Union[int, float]):
        """
        Sets a dword value in the PLC's shared memory.
        If 'value' is an int, it's treated as a uint32_t (0 to 4294967295).
        If 'value' is a float, its 32-bit IEEE 754 representation is
        reinterpreted as a uint32_t and sent.
        """
        if not self.is_connected(): raise ConnectionError("Not connected.")

        actual_uint32_value: int
        if isinstance(value, float):
            # Reinterpret float bits as uint32
            # 'f' is for C float (typically 32-bit), 'I' is for C unsigned int (typically 32-bit)
            packed_float = struct.pack('f', value)
            actual_uint32_value = struct.unpack('I', packed_float)[0]
            print(f"INFO: Reinterpreting float {value} as uint32_t: {actual_uint32_value} (0x{actual_uint32_value:08X}) for address {address}")
        elif isinstance(value, int):
            if not (0 <= value <= 4294967295):
                raise ValueError("Integer DWord value must be between 0 and 4294967295.")
            actual_uint32_value = value
        else:
            raise TypeError("Value for set_dword_value must be an int or float.")

        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")
            success = self._api.lib.set_dword_value(self.client_handle, ctypes.c_uint32(address), ctypes.c_uint32(actual_uint32_value))
        if not success:
            if not self._api.lib.is_connected(self.client_handle): self._is_connected_flag = False
            raise SendError(f"Failed to set dword value at address {address}.")
        print(f"INFO: set_dword_value(address={address}, value={value} -> uint32:{actual_uint32_value}) sent.")

    def set_lword_value(self, address: int, value: Union[int, float]):
        """
        Sets an lword value in the PLC's shared memory.
        If 'value' is an int, it's treated as a uint64_t (0 to 2^64-1).
        If 'value' is a float (Python float is typically a C double), its 64-bit
        IEEE 754 representation is reinterpreted as a uint64_t and sent.
        """
        if not self.is_connected(): raise ConnectionError("Not connected.")

        actual_uint64_value: int
        if isinstance(value, float):
            # Reinterpret double (Python float) bits as uint64
            # 'd' is for C double (typically 64-bit), 'Q' is for C unsigned long long (typically 64-bit)
            packed_double = struct.pack('d', value)
            actual_uint64_value = struct.unpack('Q', packed_double)[0]
            print(f"INFO: Reinterpreting float (double) {value} as uint64_t: {actual_uint64_value} (0x{actual_uint64_value:016X}) for address {address}")
        elif isinstance(value, int):
            if not (0 <= value <= (2**64 - 1)):
                raise ValueError("Integer LWord value out of range for uint64.")
            actual_uint64_value = value
        else:
            raise TypeError("Value for set_lword_value must be an int or float.")

        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")
            success = self._api.lib.set_lword_value(self.client_handle, ctypes.c_uint32(address), ctypes.c_uint64(actual_uint64_value))
        if not success:
            if not self._api.lib.is_connected(self.client_handle): self._is_connected_flag = False
            raise SendError(f"Failed to set lword value at address {address}.")
        print(f"INFO: set_lword_value(address={address}, value={value} -> uint64:{actual_uint64_value}) sent.")

    def request_plc_value(self, address: int, var_type: str) -> Union[bool, int, float]:
        """
        Requests a value from the PLC's shared memory.
        'var_type' can be 'bool', 'byte', 'word', 'dword', or 'lword'.
        Returns the requested value, or raises an error if the request fails.
        """
        if not self.is_connected(): raise ConnectionError("Not connected.")
        
        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")

            if var_type == 'bool':
                var_enum = 0
                print(f"INFO: Requesting BOOL value at address {address}")
                self._api.lib.request_value(self.client_handle, ctypes.c_uint32(address), var_enum)
            elif var_type == 'byte':
                var_enum = 1
                self._api.lib.request_value(self.client_handle, ctypes.c_uint32(address), var_enum)
            elif var_type == 'word':
                var_enum = 2
                self._api.lib.request_value(self.client_handle, ctypes.c_uint32(address), var_enum)
            elif var_type == 'dword':
                var_enum = 3
                self._api.lib.request_value(self.client_handle, ctypes.c_uint32(address), var_enum)
            elif var_type == 'lword':
                var_enum = 4
                self._api.lib.request_value(self.client_handle, ctypes.c_uint32(address), var_enum)
            else:
                raise ValueError(f"Invalid var_type '{var_type}'. Must be one of: 'bool', 'byte', 'word', 'dword', 'lword'.")

    def wait_for_value(self, address: int, var_type: str, timeout: int = 2) -> Union[bool, int, float]:
        """
        Waits for a value to be available in the PLC's shared memory.
        'var_type' can be 'bool', 'byte', 'word', 'dword', or 'lword'.
        Returns the requested value, or raises an error if the request times out.
        """
        if not self.is_connected(): 
            raise ConnectionError("Not connected.")
        
        self.request_plc_value(address, var_type)
        
        start_time = time.time()
        while True:
            try:
                if time.time() - start_time > timeout:
                    raise ApiError(f"Timeout waiting for value at address {address} of type '{var_type}'")
                    
                if var_type == 'bool':
                    if self._api.BoolCameFromServer.value:
                        result = ctypes.c_bool()
                        if self._api.lib.get_bool_value(self.client_handle, ctypes.c_uint32(address), ctypes.byref(result)):
                            self._api.BoolCameFromServer.value = False
                            return result.value
                elif var_type == 'byte':
                    if self._api.ByteCameFromServer.value:
                        result = ctypes.c_uint8()
                        if self._api.lib.get_byte_value(self.client_handle, ctypes.c_uint32(address), ctypes.byref(result)):
                            self._api.ByteCameFromServer.value = False
                            return result.value
                elif var_type == 'word':
                    if self._api.WordCameFromServer.value:
                        result = ctypes.c_uint16()
                        if self._api.lib.get_word_value(self.client_handle, ctypes.c_uint32(address), ctypes.byref(result)):
                            self._api.WordCameFromServer.value = False
                            return result.value
                elif var_type == 'dword':
                    if self._api.DWordCameFromServer.value:
                        result = ctypes.c_uint32()
                        if self._api.lib.get_dword_value(self.client_handle, ctypes.c_uint32(address), ctypes.byref(result)):
                            self._api.DWordCameFromServer.value = False
                            return result.value
                elif var_type == 'lword':
                    if self._api.LWordCameFromServer.value:
                        result = ctypes.c_uint64()
                        if self._api.lib.get_lword_value(self.client_handle, ctypes.c_uint32(address), ctypes.byref(result)):
                            self._api.LWordCameFromServer.value = False
                            return result.value
                else:
                    raise ValueError(f"Invalid var_type '{var_type}'. Must be one of: 'bool', 'byte', 'word', 'dword', 'lword'.")
                
                time.sleep(0.01)  # Small sleep to prevent busy waiting
                
            except Exception as e:
                raise ApiError(f"Error while waiting for value: {str(e)}")
    
    
    def get_bool_value(self, address: int) -> bool:
        """Gets a boolean value from the PLC's shared memory."""
        return self.wait_for_value(address, 'bool')

    def get_byte_value(self, address: int) -> int:
        """Gets a byte value (0-255) from the PLC's shared memory."""
        return self.wait_for_value(address, 'byte')

    def get_word_value(self, address: int) -> int:
        """Gets a word value (0-65535) from the PLC's shared memory."""
        return self.wait_for_value(address, 'word')

    def get_dword_value(self, address: int) -> int:
        """Gets a dword value (0-4294967295) from the PLC's shared memory."""
        return self.wait_for_value(address, 'dword')
        
    def get_lword_value(self, address: int) -> int:
        """Gets an lword value (0 to 2^64-1) from the PLC's shared memory."""
        return self.wait_for_value(address, 'lword')


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def __del__(self):
        if hasattr(self, 'client_handle') and self.client_handle:
            self.disconnect()


