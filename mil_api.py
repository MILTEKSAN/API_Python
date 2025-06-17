import ctypes
import platform
import threading
import time
from enum import IntEnum
import struct
from typing import Optional, Union
import os

# --- API Configuration ---
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
class VarType(IntEnum):
    BOOL = 0
    BYTE = 1
    WORD = 2
    DWORD = 3
    LWORD = 4

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

        # --- Value Requesting ---
        # <<< FIX 1: Added the missing signature for request_value. This is the main fix for the crash.
        # The third argument is an enum, which is an `int` in C.
        self.lib.request_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int]
        # Assuming it returns void or you don't care about the return value. If it returns a status, add:
        # self.lib.request_value.restype = ctypes.c_bool

        # --- Data Getters ---
        self.lib.get_bool_value.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_bool)]
        self.lib.get_bool_value.restype = ctypes.c_bool
        
        # <<< FIX 2: Added missing signatures for other getter functions to prevent future errors.
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

# --- Main Python Client Class ---
class Client:
    def __init__(self, lib_path: str = LIB_NAME):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if not os.path.isabs(lib_path):
            lib_path = os.path.join(script_dir, lib_path)
            
        self._api = _C_API(lib_path)
        self.client_handle = self._api.lib.create_client()
        if not self.client_handle:
            raise ApiError("Failed to create client instance from library.")
        
        self._is_connected_flag = False
        self._processing_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        print("INFO: Client instance created.")

    def connect(self, host: str, port: int, timeout: int = 5):
        if self._is_connected_flag:
            print("WARN: Already connected.")
            return

        with self._lock:
            if self._is_connected_flag:
                print("WARN: Already connected (race condition avoided).")
                return

            self._api.lib.connect_to_server(self.client_handle, host.encode('utf-8'), port)

            self._stop_event.clear()
            self._processing_thread = threading.Thread(target=self._message_processor)
            self._processing_thread.daemon = True
            self._processing_thread.start()

            start_time = time.time()
            while not self._api.lib.is_connected(self.client_handle):
                if time.time() - start_time > timeout:
                    self._stop_event.set()
                    if self._processing_thread and self._processing_thread.is_alive():
                        self._processing_thread.join(timeout=1.0)
                    raise ConnectionError(f"Connection to {host}:{port} timed out after {timeout} seconds.")
                if self._stop_event.is_set():
                    raise ConnectionError("Connection attempt aborted.")
                time.sleep(0.1)
            
            self._is_connected_flag = True
            print(f"INFO: Successfully connected to {host}:{port} and message processor started.")

    def _message_processor(self):
        print("INFO: Message processing thread started.")
        while not self._stop_event.is_set():
            with self._lock:
                if self.client_handle:
                    self._api.lib.process_messages(self.client_handle)
            time.sleep(0.01)
        print("INFO: Message processing thread stopped.")

    def disconnect(self):
        if not self.client_handle and not self._is_connected_flag:
            return

        print("INFO: Disconnecting...")
        self._stop_event.set()
        if self._processing_thread and self._processing_thread.is_alive():
            self._processing_thread.join(timeout=2.0)

        with self._lock:
            if not self.client_handle: return
            if self._api.lib.is_connected(self.client_handle):
                self._api.lib.disconnect_from_server(self.client_handle)
            self._api.lib.destroy_client(self.client_handle)
            self.client_handle = None
            self._is_connected_flag = False # <<< FIX 3: Corrected the variable name from self._is_connected
        
        print("INFO: Client disconnected and destroyed.")
        
    def is_connected(self) -> bool:
        with self._lock:
            if not self.client_handle or not self._is_connected_flag:
                return False
            # Re-verify with C-layer to catch unexpected disconnects
            if not self._api.lib.is_connected(self.client_handle):
                self._is_connected_flag = False
            return self._is_connected_flag
    
    def set_plc_bool(self, address: int, value: bool):
        if not self.is_connected(): raise ConnectionError("Not connected.")
        if not isinstance(value, bool): raise TypeError("Value must be a boolean.")
        
        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")
            success = self._api.lib.set_bool_value(self.client_handle, ctypes.c_uint32(address), ctypes.c_bool(value))
        if not success:
            self.is_connected() # Update internal connection flag
            raise SendError(f"Failed to set boolean value at address {address}.")
        print(f"INFO: set_plc_bool(address={address}, value={value}) sent.")

    # ... Other set_plc_* methods remain the same ...
    def set_plc_byte(self, address: int, value: int):
        if not self.is_connected(): raise ConnectionError("Not connected.")
        if not (0 <= value <= 255): raise ValueError("Byte value must be between 0 and 255.")

        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")
            success = self._api.lib.set_byte_value(self.client_handle, ctypes.c_uint32(address), ctypes.c_uint8(value))
        if not success:
            self.is_connected()
            raise SendError(f"Failed to set byte value at address {address}.")
        print(f"INFO: set_plc_byte(address={address}, value={value}) sent.")

    def set_plc_word(self, address: int, value: int):
        if not self.is_connected(): raise ConnectionError("Not connected.")
        if not (0 <= value <= 65535): raise ValueError("Word value must be between 0 and 65535.")
        
        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")
            success = self._api.lib.set_word_value(self.client_handle, ctypes.c_uint32(address), ctypes.c_uint16(value))
        if not success:
            self.is_connected()
            raise SendError(f"Failed to set word value at address {address}.")
        print(f"INFO: set_plc_word(address={address}, value={value}) sent.")

    def set_plc_dword(self, address: int, value: Union[int, float]):
        if not self.is_connected(): raise ConnectionError("Not connected.")

        actual_uint32_value: int
        if isinstance(value, float):
            packed_float = struct.pack('f', value)
            actual_uint32_value = struct.unpack('I', packed_float)[0]
        elif isinstance(value, int):
            if not (0 <= value <= 4294967295):
                raise ValueError("Integer DWord value must be between 0 and 4294967295.")
            actual_uint32_value = value
        else:
            raise TypeError("Value for set_plc_dword must be an int or float.")

        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")
            success = self._api.lib.set_dword_value(self.client_handle, ctypes.c_uint32(address), ctypes.c_uint32(actual_uint32_value))
        if not success:
            self.is_connected()
            raise SendError(f"Failed to set dword value at address {address}.")
        print(f"INFO: set_plc_dword(address={address}, value={value} -> uint32:{actual_uint32_value}) sent.")

    def set_plc_lword(self, address: int, value: Union[int, float]):
        if not self.is_connected(): raise ConnectionError("Not connected.")

        actual_uint64_value: int
        if isinstance(value, float):
            packed_double = struct.pack('d', value)
            actual_uint64_value = struct.unpack('Q', packed_double)[0]
        elif isinstance(value, int):
            if not (0 <= value <= (2**64 - 1)):
                raise ValueError("Integer LWord value out of range for uint64.")
            actual_uint64_value = value
        else:
            raise TypeError("Value for set_plc_lword must be an int or float.")

        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")
            success = self._api.lib.set_lword_value(self.client_handle, ctypes.c_uint32(address), ctypes.c_uint64(actual_uint64_value))
        if not success:
            self.is_connected()
            raise SendError(f"Failed to set lword value at address {address}.")
        print(f"INFO: set_plc_lword(address={address}, value={value} -> uint64:{actual_uint64_value}) sent.")
    # ... Other set_plc_* methods end ...

    def request_plc_value(self, address: int, var_type_str: str):
        if not self.is_connected():
            raise ConnectionError("Not connected.")
        
        try:
            var_enum = VarType[var_type_str.upper()]
        except KeyError:
            raise ValueError(f"Invalid variable type string: {var_type_str}")
        
        with self._lock:
            if not self.client_handle: raise ConnectionError("Client handle destroyed.")
            # This call is now safe because its signature is defined.
            self._api.lib.request_value(self.client_handle, ctypes.c_uint32(address), var_enum)

    # --- Getter Methods ---
    def get_bool_value(self, address: int) -> bool:
        """Gets a boolean value from the PLC's shared memory."""
        if not self.is_connected(): raise ConnectionError("Not connected.")
        bool_value = ctypes.c_bool()
        # <<< FIX 4: Corrected the recursive call to call the C API function
        if self._api.lib.get_bool_value(self.client_handle, ctypes.c_uint32(address), ctypes.byref(bool_value)):
            return bool_value.value
        else:
            self.is_connected() # Update internal connection status
            raise ApiError(f"Failed to get boolean value at address {address}.")

    def get_byte_value(self, address: int) -> int:
        if not self.is_connected(): raise ConnectionError("Not connected.")
        byte_value = ctypes.c_uint8()
        if self._api.lib.get_byte_value(self.client_handle, ctypes.c_uint32(address), ctypes.byref(byte_value)):
            return byte_value.value
        else:
            self.is_connected()
            raise ApiError(f"Failed to get byte value at address {address}.")

    def get_word_value(self, address: int) -> int:
        if not self.is_connected(): raise ConnectionError("Not connected.")
        word_value = ctypes.c_uint16()
        if self._api.lib.get_word_value(self.client_handle, ctypes.c_uint32(address), ctypes.byref(word_value)):
            return word_value.value
        else:
            self.is_connected()
            raise ApiError(f"Failed to get word value at address {address}.")

    def get_dword_value(self, address: int) -> int:
        if not self.is_connected(): raise ConnectionError("Not connected.")
        dword_value = ctypes.c_uint32()
        if self._api.lib.get_dword_value(self.client_handle, ctypes.c_uint32(address), ctypes.byref(dword_value)):
            return dword_value.value
        else:
            self.is_connected()
            raise ApiError(f"Failed to get dword value at address {address}.")
        
    def get_lword_value(self, address: int) -> int:
        if not self.is_connected(): raise ConnectionError("Not connected.")
        lword_value = ctypes.c_uint64()
        if self._api.lib.get_lword_value(self.client_handle, ctypes.c_uint32(address), ctypes.byref(lword_value)):
            return lword_value.value
        else:
            self.is_connected()
            raise ApiError(f"Failed to get lword value at address {address}.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def __del__(self):
        # The __del__ method is a fallback. The `with` statement is more reliable.
        if hasattr(self, 'client_handle') and self.client_handle:
            # We must check if the thread is alive because in some shutdown scenarios
            # the threading module might already be cleaned up.
            if self._stop_event and self._processing_thread and self._processing_thread.is_alive():
                self.disconnect()