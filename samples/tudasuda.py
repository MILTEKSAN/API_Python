import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
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
    """Tkinter GUI to write target position and monitor feedback (position + power)."""

    def __init__(self, root):
        self.root = root
        self.root.title("MilConnAPI Controls")
        self.root.geometry("480x280")

        self.client: Client | None = None
        self.is_connected = False
        self.host_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="60000")
        self.status_var = tk.StringVar(value="🔌 Disconnected")

        # Data variables
        self.position_var = tk.DoubleVar(value=0.0)
        self.feedback_var = tk.DoubleVar(value=0.0)
        self.power_state = False
        self.power_feedback = tk.BooleanVar(value=False)

        self.stop_thread = threading.Event()

        self._create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # -------------------------------------------------------------------------
    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Connection Frame ---
        conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding=10)
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, padx=5, sticky=tk.W)
        ttk.Entry(conn_frame, textvariable=self.host_var, width=15).grid(row=0, column=1, padx=5)
        ttk.Label(conn_frame, text="Port:").grid(row=0, column=2, padx=5, sticky=tk.W)
        ttk.Entry(conn_frame, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=5)
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self._toggle_connection)
        self.connect_btn.grid(row=0, column=4, padx=5)

        # --- Power & Execute Control ---
        power_frame = ttk.LabelFrame(main_frame, text="Power / Execute Control", padding=10)
        power_frame.pack(fill=tk.X, pady=(0, 10))

        # Power button
        self.power_btn = ttk.Button(power_frame, text="Power OFF", command=self._toggle_power)
        self.power_btn.grid(row=0, column=0, padx=5, sticky=tk.W)

        # Power LED indicator
        self.power_led = tk.Canvas(power_frame, width=20, height=20, highlightthickness=1, highlightbackground="gray")
        self.power_led.grid(row=0, column=1, padx=10)
        self._update_led(self.power_feedback.get())

        # Execute button (momentary)
        self.execute_btn = ttk.Button(power_frame, text="Execute")
        self.execute_btn.grid(row=0, column=2, padx=20, sticky=tk.W)
        self.execute_btn.bind("<ButtonPress>", lambda e: self._execute_press())
        self.execute_btn.bind("<ButtonRelease>", lambda e: self._execute_release())

        # --- Position Control ---
        pos_frame = ttk.LabelFrame(main_frame, text="Position Control", padding=10)
        pos_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(pos_frame, text="Target Pos:").grid(row=0, column=0, padx=5)
        ttk.Entry(pos_frame, textvariable=self.position_var, width=10).grid(row=0, column=1, padx=5)
        ttk.Button(pos_frame, text="Write", command=self._write_position).grid(row=0, column=2, padx=5)

        ttk.Label(pos_frame, text="Feedback:").grid(row=1, column=0, padx=5)
        ttk.Label(pos_frame, textvariable=self.feedback_var, width=12).grid(row=1, column=1, padx=5)

        # --- Status Bar ---
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self._update_ui_state()

    # -------------------------------------------------------------------------
    def _update_led(self, state: bool):
        """Update LED color for power feedback."""
        self.power_led.delete("all")
        color = "green" if state else "red"
        self.power_led.create_oval(2, 2, 18, 18, fill=color)

    # -------------------------------------------------------------------------
    def _write_position(self):
        """Send position value to address 1."""
        if not self.is_connected or not self.client:
            messagebox.showwarning("Not Connected", "Connect to the PLC first.")
            return
        try:
            value = float(self.position_var.get())
            self.client.set_lword_value(1, value)
            self.status_var.set(f"✅ Sent Position {value:.2f} to Addr 1")
        except Exception as e:
            messagebox.showerror("Send Error", f"Failed to write position.\n\n{e}")

    # -------------------------------------------------------------------------
    def _toggle_power(self):
        """Toggle power BOOL at address 0."""
        if not self.is_connected or not self.client:
            messagebox.showwarning("Not Connected", "Connect to the PLC first.")
            return
        try:
            self.power_state = not self.power_state
            self.client.set_bool_value(0, self.power_state)
            self.power_btn.config(text="Power ON" if not self.power_state else "Power OFF")
            self.status_var.set(f"⚡ Power {'ON' if self.power_state else 'OFF'} sent to Addr 0")
        except Exception as e:
            messagebox.showerror("Send Error", f"Failed to toggle power.\n\n{e}")

    # -------------------------------------------------------------------------
    def _execute_press(self):
        """Send BOOL True when Execute button pressed."""
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_bool_value(1, True)
            self.status_var.set("▶ Execute = True (Pressed)")
        except Exception as e:
            self.status_var.set(f"Execute press error: {e}")

    def _execute_release(self):
        """Send BOOL False when Execute button released."""
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_bool_value(1, False)
            self.status_var.set("⏹ Execute = False (Released)")
        except Exception as e:
            self.status_var.set(f"Execute release error: {e}")

    # -------------------------------------------------------------------------
    def _start_feedback_thread(self):
        """Start background thread for feedback reading."""
        if hasattr(self, "feedback_thread") and self.feedback_thread.is_alive():
            return
        self.stop_thread.clear()
        self.feedback_thread = threading.Thread(target=self._feedback_loop, daemon=True)
        self.feedback_thread.start()

    def _feedback_loop(self):
        """Loop reading position and power feedback from PLC."""
        while not self.stop_thread.is_set():
            if self.is_connected and self.client:
                try:
                    power_fb = self.client.get_bool_value(80)
                    pos = self.client.get_lword_value(100)
                    self.root.after(0, self.feedback_var.set, pos)
                    self.root.after(0, self.power_feedback.set, power_fb)
                    self.root.after(0, self._update_led, power_fb)
                except Exception as e:
                    self.root.after(0, self.status_var.set, f"Feedback error: {e}")
            time.sleep(0.2)

    # -------------------------------------------------------------------------
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
            self._start_feedback_thread()
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
        self.stop_thread.set()
        if self.client:
            self.client.disconnect()
            self.client = None
        self.status_var.set("🔌 Disconnected")
        self._update_ui_state()

    def _update_ui_state(self):
        state = tk.NORMAL if self.is_connected else tk.DISABLED
        self.connect_btn.config(text="Disconnect" if self.is_connected else "Connect")
        self.power_btn.config(state=state)
        self.execute_btn.config(state=state)
        self.root.update_idletasks()

    def _on_closing(self):
        self._disconnect()
        self.root.destroy()


# -------------------------------------------------------------------------
if __name__ == "__main__":
    if Client:
        root = tk.Tk()
        app = MilConnApp(root)
        root.mainloop()
    else:
        print("--- GUI cannot start due to API load failure. ---")
