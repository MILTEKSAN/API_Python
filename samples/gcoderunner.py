import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading, time
import sys, os
import struct
from collections import deque

# Matplotlib (TkAgg backend)
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

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


class MilteksanGCodeApp:
    def __init__(self, root):
        # Root & window
        self.root = root
        self.root.title("Milteksan G-Code Loader")
        self.root.geometry("1100x720")

        # Runtime state
        self.client: Client | None = None
        self.polling = False
        self.current_line = -1
        self.power_state = False  # Track current power state

        # XY buffer for plot
        self.buffer_size = 500
        self.xy_buffer = deque(maxlen=self.buffer_size)

        # Build UI
        self._build_ui()

    # ---------------- UI Setup ----------------
    def _build_ui(self):
        # --- Connection row ---
        conn_frame = ttk.Frame(self.root)
        conn_frame.pack(fill="x", padx=10, pady=6)

        ttk.Label(conn_frame, text="IP:").pack(side="left", padx=(0, 4))
        self.ip_entry = ttk.Entry(conn_frame, width=15)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.pack(side="left")

        ttk.Label(conn_frame, text="Port:").pack(side="left", padx=(10, 4))
        self.port_entry = ttk.Entry(conn_frame, width=8)
        self.port_entry.insert(0, "60000")
        self.port_entry.pack(side="left")

        ttk.Button(conn_frame, text="Connect", command=self.connect_api).pack(side="left", padx=5)
        ttk.Button(conn_frame, text="Disconnect", command=self.disconnect_api).pack(side="left", padx=5)

        self.status = ttk.Label(conn_frame, text="Disconnected", foreground="red")
        self.status.pack(side="right")

        # --- Control Buttons Row ---
        ctrl_frame = ttk.Frame(self.root)
        ctrl_frame.pack(fill="x", padx=10, pady=4)

        self.power_button = ttk.Button(ctrl_frame, text="Power On", command=self.toggle_power)
        self.power_button.pack(side="left", padx=5)

        ttk.Button(ctrl_frame, text="💾 Save G-Code", command=self.save_gcode).pack(side="left", padx=5)

        # Momentary buttons (press->True, release->False)
        self.load_btn = ttk.Button(ctrl_frame, text="📂 Load G-Code")
        self.load_btn.pack(side="left", padx=5)
        self.load_btn.bind("<ButtonPress-1>",  lambda e: self._set_bool(2, True))
        self.load_btn.bind("<ButtonRelease-1>", lambda e: self._set_bool(2, False))

        self.start_btn = ttk.Button(ctrl_frame, text="▶ Start")
        self.start_btn.pack(side="left", padx=5)
        self.start_btn.bind("<ButtonPress-1>",  lambda e: self._set_bool(3, True))
        self.start_btn.bind("<ButtonRelease-1>", lambda e: self._set_bool(3, False))

        self.hold_btn = ttk.Button(ctrl_frame, text="⏸ Hold")
        self.hold_btn.pack(side="left", padx=5)
        self.hold_btn.bind("<ButtonPress-1>",  lambda e: self._set_bool(4, True))
        self.hold_btn.bind("<ButtonRelease-1>", lambda e: self._set_bool(4, False))

        self.reset_btn = ttk.Button(ctrl_frame, text="🔁 Reset")
        self.reset_btn.pack(side="left", padx=5)
        self.reset_btn.bind("<ButtonPress-1>",  lambda e: self._set_bool(5, True))
        self.reset_btn.bind("<ButtonRelease-1>", lambda e: self._set_bool(5, False))

        self.pos_label = ttk.Label(ctrl_frame, text="X: 0.000  Y: 0.000")
        self.pos_label.pack(side="right", padx=10)

        # --- Power LED row ---
        led_frame = ttk.Frame(self.root)
        led_frame.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(led_frame, text="Power Status:").pack(side="left")
        self.power_led = tk.Canvas(led_frame, width=20, height=20, highlightthickness=0)
        self.led_circle = self.power_led.create_oval(2, 2, 18, 18, fill="red")
        self.power_led.pack(side="left", padx=6)

        # --- Split main area: left editor / right plot ---
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Left: G-code editor with scrollbars
        left_frame = ttk.Frame(paned)
        self.text = tk.Text(left_frame, wrap="none", font=("Consolas", 12))
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("running", background="#FFDD88")

        yscroll = ttk.Scrollbar(left_frame, command=self.text.yview)
        yscroll.pack(side="right", fill="y")
        xscroll = ttk.Scrollbar(left_frame, command=self.text.xview, orient="horizontal")
        xscroll.pack(side="bottom", fill="x")

        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        paned.add(left_frame, weight=3)

        # Right: Matplotlib plot
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)

        self.fig = Figure(figsize=(5, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self._configure_axes()

        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _configure_axes(self):
        self.ax.clear()
        self.ax.set_title("X-Y Path")
        self.ax.set_xlabel("X Position")
        self.ax.set_ylabel("Y Position")
        self.ax.grid(True)
        # Not setting limits → autoscale

    # ---------------- API Connection ----------------
    def connect_api(self):
        ip = self.ip_entry.get().strip()
        try:
            port = int(self.port_entry.get())
        except ValueError:
            messagebox.showerror("Invalid Port", "Port number must be an integer.")
            return

        try:
            self.client = Client()
            self.client.connect(ip, port)
            self.status.config(text="Connected", foreground="green")
            self.polling = True
            threading.Thread(target=self.poll_values, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    def disconnect_api(self):
        self.polling = False
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
        self.status.config(text="Disconnected", foreground="red")

    # ---------------- Button Commands ----------------
    def toggle_power(self):
        """Toggle power state On/Off."""
        if not self.client or not self.client.is_connected():
            messagebox.showwarning("Warning", "Not connected to the server.")
            return

        new_state = not self.power_state
        try:
            self.client.set_bool_value(0, new_state)
            self.power_state = new_state
            self.power_button.config(text="Power Off" if new_state else "Power On")
        except (SendError, ConnectionError) as e:
            print(f"Error setting power: {e}")

    def save_gcode(self):
        """Save current editor text to fixed file /home/fehim/NC_Program.txt."""
        save_path = "/home/fehim/NC_Program.txt"
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            data = self.text.get("1.0", tk.END).strip()
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(data)
            print(f"INFO: G-Code saved to {save_path}")
        except Exception as e:
            print(f"ERROR: Failed to save G-Code -> {e}")

    def load_gcode(self):
        self._pulse_bool(2)

    def start_gcode(self):
        self._pulse_bool(3)

    def hold_gcode(self):
        self._pulse_bool(4)

    def reset_gcode(self):
        """Reset logic + clear plot + clear line highlight."""
        self._pulse_bool(5)            # Send reset to machine/PLC
        self.highlight_line(-1)        # Remove highlighted line
        self.xy_buffer.clear()         # ✅ Clear stored XY path
        self.reset_plot()              # ✅ Clear the drawing
        
    def reset_plot(self):
        """Clear the XY plot completely."""
        self.ax.clear()
        self.ax.set_title("X-Y Path")
        self.ax.set_xlabel("X Position")
        self.ax.set_ylabel("Y Position")
        self.ax.grid(True)
        self.canvas.draw_idle()
        
    # ---------------- Data Polling ----------------
    def poll_values(self):
        """Polls line number, X/Y position, and power LED state."""
        while self.polling and self.client and self.client.is_connected():
            try:
                # G-code current line (DWORD)
                line_num = self.client.get_dword_value(1)

                # Positions: little-endian 64-bit unsigned -> double
                raw_x = self.client.get_lword_value(100)  # 64-bit
                raw_y = self.client.get_lword_value(101)

                x = struct.unpack('<d', struct.pack('<Q', raw_x))[0]
                y = struct.unpack('<d', struct.pack('<Q', raw_y))[0]

                # Power LED
                power_on = self.client.get_bool_value(80)

                # Schedule UI update on main thread
                self.update_ui(line_num, x, y, power_on)
            except Exception:
                # Avoid spamming; just continue polling
                pass

            time.sleep(0.2)

    def update_ui(self, line_num, x, y, power_on):
        self.root.after(0, lambda: self._update_ui(line_num, x, y, power_on))

    def _update_ui(self, line_num, x, y, power_on):
        # Position label
        self.pos_label.config(text=f"X: {x:.3f}  Y: {y:.3f}")

        # Append to XY buffer & draw
        self.xy_buffer.append((x, y))
        self.draw_xy_path()

        # Power LED + button text sync
        self.set_led_state(power_on)
        if power_on != self.power_state:
            self.power_state = power_on
            self.power_button.config(text="Power Off" if power_on else "Power On")

        # G-code line highlight
        if line_num != self.current_line:
            self.current_line = line_num
            self.highlight_line(line_num)

    # ---------------- Plotting ----------------
    def draw_xy_path(self):
        if len(self.xy_buffer) < 2:
            return
        xs, ys = zip(*self.xy_buffer)

        self._configure_axes()
        self.ax.plot(xs, ys, linewidth=1)
        # Current toolhead dot
        self.ax.plot(xs[-1], ys[-1], marker='o')

        self.canvas.draw_idle()

    # ---------------- UI Helpers ----------------
    def set_led_state(self, on: bool):
        color = "lime green" if on else "red"
        self.power_led.itemconfig(self.led_circle, fill=color)

    def highlight_line(self, line_num: int):
        """Highlight current G-code line in the text widget."""
        self.text.tag_remove("running", "1.0", tk.END)
        if line_num <= 0:
            return

        # Total lines in editor
        try:
            total_lines_str = self.text.index('end-1c').split('.')[0]
            total_lines = int(total_lines_str)
        except Exception:
            total_lines = 0

        if 1 <= line_num <= total_lines:
            start = f"{line_num}.0"
            end = f"{line_num}.end"
            self.text.tag_add("running", start, end)
            self.text.see(start)

    def _set_bool(self, addr: int, value: bool):
        """Send a bool value without delay (for press/release)."""
        try:
            if self.client and self.client.is_connected():
                self.client.set_bool_value(addr, value)
        except (SendError, ConnectionError) as e:
            print(f"Error writing bool {addr}: {e}")

    # ---------------- Helpers ----------------
    def _pulse_bool(self, addr: int):
        """Sets a bool True for 100ms then False."""
        try:
            if not self.client or not self.client.is_connected():
                return
            self.client.set_bool_value(addr, True)
            time.sleep(0.1)
            self.client.set_bool_value(addr, False)
        except (SendError, ConnectionError) as e:
            print(f"Error toggling bool {addr}: {e}")


# ---------------- Run ----------------
if __name__ == "__main__":
    root = tk.Tk()
    app = MilteksanGCodeApp(root)
    root.mainloop()
