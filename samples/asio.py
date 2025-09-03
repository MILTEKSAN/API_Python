import tkinter as tk
from tkinter import ttk, messagebox, font
import queue
import threading
import time

# --- Import the new API Client and its exceptions ---
try:
    # Make sure the updated milapi.py is in the same folder or in the Python path
    # NOTE: This example assumes your mil_api.Client has 'get_plc_dword(address)'
    # and set_plc_<type> methods.
    from mil_api import Client, ApiError, ConnectionError, SendError
except (ImportError, OSError) as e:
    # This block creates a popup if the DLL/API module fails to load.
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Startup Error",
        "Failed to load the required API module (milapi.py) or its library (milconn.dll/so).\n"
        "Ensure both files are in the correct folder.\n\n"
        f"Details: {e}"
    )
    Client = None # Set Client to None to prevent the app from running

class MilConnApp:
    """A Tkinter GUI application to monitor specific DWORDs and send various data types."""
    def __init__(self, root):
        self.root = root
        self.root.title("MilConnAPI DWORD Monitor & Commander")
        self.root.geometry("550x500") # Adjusted size
        self.root.minsize(450, 450)

        # --- Application State ---
        self.client: Client | None = None
        self.is_connected = False
        
        # --- Threading for UI Updates ---
        self.ui_update_queue = queue.Queue()
        self.updater_thread: threading.Thread | None = None
        
        # --- Tkinter Variables ---
        # Variables for reading DWORDs 1, 2, and 3
        self.dword1_var = tk.StringVar(value="---")
        self.dword2_var = tk.StringVar(value="---")
        self.dword3_var = tk.StringVar(value="---")

        # Connection and command variables
        self.host_var = tk.StringVar(value="192.168.1.254")
        self.port_var = tk.StringVar(value="60000")
        self.status_var = tk.StringVar(value="🔌 Disconnected")
        self.address_var = tk.StringVar(value="100")
        self.value_var = tk.StringVar(value="0")

        self._create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Start the loop that processes items from the UI queue.
        self.root.after(100, self._process_ui_queue)

    def _create_widgets(self):
        """Sets up the entire GUI layout."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(2, weight=0)
        main_frame.columnconfigure(0, weight=1)

        # --- Connection Frame ---
        conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="10")
        conn_frame.grid(row=0, column=0, sticky=tk.EW)
        conn_frame.columnconfigure(1, weight=1)
        conn_frame.columnconfigure(2, weight=0)

        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(conn_frame, textvariable=self.host_var).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Label(conn_frame, text="Port:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(conn_frame, textvariable=self.port_var).grid(row=1, column=1, sticky=tk.EW, padx=5)
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self._toggle_connection)
        self.connect_btn.grid(row=0, column=2, rowspan=2, sticky="ns", padx=5, ipady=5)
        
        # --- Live PLC DWORDs Frame ---
        read_frame = ttk.LabelFrame(main_frame, text="Live PLC DWORDs", padding="10")
        read_frame.grid(row=1, column=0, sticky=tk.EW, pady=10)
        read_frame.columnconfigure(1, weight=1)
        bold_font = font.nametofont("TkDefaultFont").copy()
        bold_font.configure(weight="bold", size=12)

        ttk.Label(read_frame, text="DWORD 1:", font=bold_font).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(read_frame, textvariable=self.dword1_var, font=bold_font, foreground="blue").grid(row=0, column=1, sticky=tk.W)
        ttk.Label(read_frame, text="DWORD 2:", font=bold_font).grid(row=1, column=0, sticky=tk.W)
        ttk.Label(read_frame, textvariable=self.dword2_var, font=bold_font, foreground="blue").grid(row=1, column=1, sticky=tk.W)
        ttk.Label(read_frame, text="DWORD 3:", font=bold_font).grid(row=2, column=0, sticky=tk.W)
        ttk.Label(read_frame, textvariable=self.dword3_var, font=bold_font, foreground="blue").grid(row=2, column=1, sticky=tk.W)
        
        # --- Command Frame (Restored to original) ---
        self.control_frame = ttk.LabelFrame(main_frame, text="Send PLC Write Command", padding="10")
        self.control_frame.grid(row=2, column=0, sticky=tk.EW)
        self.control_frame.columnconfigure(1, weight=1)

        ttk.Label(self.control_frame, text="Address:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(self.control_frame, textvariable=self.address_var).grid(row=0, column=1, columnspan=5, sticky=tk.EW, padx=5)
        ttk.Label(self.control_frame, text="Value:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(self.control_frame, textvariable=self.value_var).grid(row=1, column=1, columnspan=5, sticky=tk.EW, padx=5)
        
        button_frame = ttk.Frame(self.control_frame)
        button_frame.grid(row=2, column=0, columnspan=6, pady=(10,0))
        data_types = ["BOOL", "BYTE", "WORD", "DWORD", "LWORD"]
        for i, dtype in enumerate(data_types):
            btn = ttk.Button(button_frame, text=f"Send {dtype}", command=lambda dt=dtype: self._send_data(dt))
            btn.grid(row=0, column=i, padx=2, sticky=tk.EW)
            button_frame.columnconfigure(i, weight=1)

        # --- Status Bar ---
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._update_ui_state()

    def _ui_updater_loop(self):
        """
        Runs in a background thread to periodically request DWORD values.
        """
        while self.is_connected:
            try:
                # 1. Ask the server for the three DWORD values.
                dword1 = self.client.get_dword_value(1)
                dword2 = self.client.get_dword_value(2)
                dword3 = self.client.get_dword_value(3)
                
                # 2. Put the result into the queue for the UI thread.
                self.ui_update_queue.put(("update_dwords", (dword1, dword2, dword3)))
                
                # 3. Wait before the next update cycle.
                self.client.request_plc_value(1, "dword")
                self.client.request_plc_value(2, "dword")
                self.client.request_plc_value(3, "dword")
                time.sleep(0.5) 
            except (ApiError, ConnectionError, SendError) as e:
                if self.is_connected:
                    self.ui_update_queue.put(("error", f"Connection lost: {e}"))
                break 
        print("INFO: UI updater thread has stopped.")

    def _process_ui_queue(self):
        """
        Checks the queue for data from the background thread and updates the GUI.
        """
        try:
            while not self.ui_update_queue.empty():
                event_type, data = self.ui_update_queue.get_nowait()
                
                if event_type == "update_dwords":
                    self._handle_dword_update(data)
                elif event_type == "error":
                    if self.is_connected:
                        messagebox.showerror("Communication Error", data)
                        self._disconnect() 
        finally:
            self.root.after(100, self._process_ui_queue)
    
    def _handle_dword_update(self, data):
        """Updates the DWORD value labels in the UI."""
        dword1, dword2, dword3 = data
        self.dword1_var.set(f"{dword1}")
        self.dword2_var.set(f"{dword2}")
        self.dword3_var.set(f"{dword3}")

    def _toggle_connection(self):
        """Connects or disconnects based on the current state."""
        if self.is_connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        """Handles the connection logic."""
        host, port_str = self.host_var.get(), self.port_var.get()
        try:
            port = int(port_str)
            self.status_var.set(f"🚀 Connecting to {host}:{port}...")
            self.root.update_idletasks()
            
            self.client = Client()
            self.client.connect(host, port)
            
            self.is_connected = True
            self.status_var.set(f"✅ Connected to {host}:{port}")
            
            self.updater_thread = threading.Thread(target=self._ui_updater_loop, daemon=True)
            self.updater_thread.start()

        except (ApiError, ValueError) as e:
            if self.client: self.client.disconnect()
            self.client = None
            self.is_connected = False
            self.status_var.set("❌ Connection failed")
            messagebox.showerror("Connection Error", str(e))
        
        self._update_ui_state()

    def _disconnect(self):
        """Handles the disconnection logic."""
        self.is_connected = False
        
        if self.client:
            self.client.disconnect()
            self.client = None
        
        self.status_var.set("🔌 Disconnected")
        self.dword1_var.set("---")
        self.dword2_var.set("---")
        self.dword3_var.set("---")
        self._update_ui_state()

    def _send_data(self, data_type):
        """Sends a user-defined PLC write command (Restored to original)."""
        if not self.is_connected or not self.client:
            messagebox.showwarning("Not Connected", "You must be connected to send a command.")
            return

        try:
            address = int(self.address_var.get())
            value_str = self.value_var.get()
            value: any 

            if data_type == "BOOL":
                try:
                    value = bool(int(value_str))
                except ValueError:
                    if value_str.lower() == 'true':
                        value = True
                    elif value_str.lower() == 'false':
                        value = False
                    else:
                        raise ValueError("BOOL value must be 0, 1, 'True', or 'False'")
            elif data_type == "DWORD" or data_type == "LWORD":
                if '.' in value_str or 'e' in value_str.lower():
                    value = float(value_str)
                else:
                    value = int(value_str)
            else: # For BYTE, WORD
                value = int(value_str)

            # Call the appropriate helper method from the updated mil_api.Client
            if   data_type == "BOOL": self.client.set_plc_bool(address, value)
            elif data_type == "BYTE": self.client.set_plc_byte(address, value)
            elif data_type == "WORD": self.client.set_plc_word(address, value)
            elif data_type == "DWORD": self.client.set_plc_dword(address, value)
            elif data_type == "LWORD": self.client.set_plc_lword(address, value)
            
            self.status_var.set(f"✅ Sent {data_type} ({value}) to adr {address}")
        except (ValueError, TypeError) as e:
            messagebox.showerror("Input Error", f"Address must be an integer. Value for {data_type} is invalid or out of range.\nInput: '{value_str}'\n\nDetails: {e}")
        except (ApiError, SendError) as e:
            messagebox.showerror("Send Error", f"Failed to send {data_type}.\n\n{e}")
        except Exception as e:
            messagebox.showerror("Unexpected Error", f"An error occurred while sending {data_type}.\n\n{e}")

    def _update_ui_state(self):
        """Enables or disables widgets based on connection status."""
        state = tk.NORMAL if self.is_connected else tk.DISABLED
        self.connect_btn.config(text="Disconnect" if self.is_connected else "Connect")
        for child in self.control_frame.winfo_children():
            if isinstance(child, ttk.Frame):
                for btn in child.winfo_children(): btn.config(state=state)
            elif hasattr(child, 'config'):
                child.config(state=state)

    def _on_closing(self):
        """Ensures a clean shutdown when the window is closed."""
        self._disconnect()
        self.root.destroy()

if __name__ == "__main__":
    if Client:
        root = tk.Tk()
        app = MilConnApp(root)
        root.mainloop()
    else:
        print("--- GUI cannot start due to API load failure. ---")