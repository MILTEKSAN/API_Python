import tkinter as tk
from tkinter import ttk, messagebox

# --- Import API Client ---
try:
    from mil_api import Client, ApiError, ConnectionError, SendError
except (ImportError, OSError) as e:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Startup Error",
        "Failed to load the required API module (milapi.py) or its library.\n"
        "Ensure both files are in the correct folder.\n\n"
        f"Details: {e}"
    )
    Client = None


class MilConnApp:
    """A Tkinter GUI for controlling Start, Pause, Reset, Edit, Auto with press/release,
    plus an ON/OFF toggle button for address 85."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("MilConnAPI Controls")
        self.root.geometry("500x220")

        self.client: Client | None = None
        self.is_connected = False
        self.host_var = tk.StringVar(value="192.168.1.254")
        self.port_var = tk.StringVar(value="60000")
        self.status_var = tk.StringVar(value="🔌 Disconnected")

        # Toggle state for address 85
        self.toggle_state_85 = False

        self._create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _create_widgets(self):
        """Build the GUI layout."""
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Connection Frame
        conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding=10)
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Entry(conn_frame, textvariable=self.host_var, width=15).grid(row=0, column=1, padx=5)
        ttk.Label(conn_frame, text="Port:").grid(row=0, column=2, sticky=tk.W, padx=5)
        ttk.Entry(conn_frame, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=5)
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self._toggle_connection)
        self.connect_btn.grid(row=0, column=4, padx=5)

        # Press/Release BOOL Buttons
        btn_frame = ttk.LabelFrame(main_frame, text="BOOL Controls (Press/Release)", padding=10)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        special_buttons = [
            ("Start", 82),
            ("Pause", 83),
            ("Reset", 84),
            ("Edit", 80),
            ("Auto", 81),
        ]
        for i, (label, addr) in enumerate(special_buttons):
            btn = ttk.Button(btn_frame, text=label)
            btn.grid(row=0, column=i, padx=5, sticky=tk.EW)
            btn.bind("<ButtonPress>", lambda e, a=addr: self._special_button_press(a))
            btn.bind("<ButtonRelease>", lambda e, a=addr: self._special_button_release(a))
            btn_frame.columnconfigure(i, weight=1)

        # Toggle Button for address 85
        toggle_frame = ttk.LabelFrame(main_frame, text="Toggle Control", padding=10)
        toggle_frame.pack(fill=tk.X, pady=(0, 10))
        self.toggle_btn = ttk.Button(toggle_frame, text="ON/OFF [OFF]", command=self._toggle_85)
        self.toggle_btn.pack(fill=tk.X, padx=5)

        # Status Bar
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._update_ui_state()

    def _toggle_connection(self):
        if self.is_connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        host, port_str = self.host_var.get(), self.port_var.get()
        try:
            port = int(port_str)
            self.status_var.set(f"🚀 Connecting to {host}:{port}...")
            self.root.update_idletasks()

            self.client = Client()
            self.client.connect(host, port)

            self.is_connected = True
            self.status_var.set(f"✅ Connected to {host}:{port}")
        except (ApiError, ValueError) as e:
            if self.client:
                self.client.disconnect()
            self.client = None
            self.is_connected = False
            self.status_var.set("❌ Connection failed")
            messagebox.showerror("Connection Error", str(e))
        self._update_ui_state()

    def _disconnect(self):
        self.is_connected = False
        if self.client:
            self.client.disconnect()
            self.client = None
        self.status_var.set("🔌 Disconnected")
        self._update_ui_state()

    def _special_button_press(self, address: int):
        """Send True when special button is pressed."""
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_plc_bool(address, True)
            self.status_var.set(f"✅ BOOL {address} set to True")
        except (ApiError, SendError) as e:
            messagebox.showerror("Send Error", f"Failed to send BOOL {address} = True.\n\n{e}")

    def _special_button_release(self, address: int):
        """Send False when special button is released."""
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_plc_bool(address, False)
            self.status_var.set(f"✅ BOOL {address} set to False")
        except (ApiError, SendError) as e:
            messagebox.showerror("Send Error", f"Failed to send BOOL {address} = False.\n\n{e}")

    def _toggle_85(self):
        """Toggle BOOL at address 85."""
        if not self.is_connected or not self.client:
            messagebox.showwarning("Not Connected", "Connect to the PLC first.")
            return

        try:
            self.toggle_state_85 = not self.toggle_state_85
            self.client.set_plc_bool(85, self.toggle_state_85)
            state_str = "ON" if self.toggle_state_85 else "OFF"
            self.toggle_btn.config(text=f"ON/OFF [{state_str}]")
            self.status_var.set(f"✅ BOOL 85 set to {self.toggle_state_85}")
        except (ApiError, SendError) as e:
            messagebox.showerror("Send Error", f"Failed to toggle BOOL 85.\n\n{e}")

    def _update_ui_state(self):
        """Enable or disable controls depending on connection status."""
        state = tk.NORMAL if self.is_connected else tk.DISABLED
        self.connect_btn.config(text="Disconnect" if self.is_connected else "Connect")
        for child in self.root.winfo_children():
            if isinstance(child, ttk.LabelFrame) and "BOOL Controls" in str(child.cget("text")):
                for btn in child.winfo_children():
                    btn.config(state=state)
        self.toggle_btn.config(state=state)

    def _on_closing(self):
        self._disconnect()
        self.root.destroy()


if __name__ == "__main__":
    if Client:
        root = tk.Tk()
        app = MilConnApp(root)
        root.mainloop()
    else:
        print("--- GUI cannot start due to API load failure. ---")
