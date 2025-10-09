import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os
import sys
import struct
from collections import deque

# Matplotlib embedding
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


class MilConnApp:
    """Tkinter GUI to control servo via MilConnAPI."""

    def __init__(self, root):
        self.root = root
        self.root.title("MilConnAPI Controls")
        self.root.geometry("720x850")

        self.client: Client | None = None
        self.is_connected = False
        self.host_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="60000")
        self.status_var = tk.StringVar(value="🔌 Disconnected")

        self.position_var = tk.DoubleVar(value=0.0)
        self.feedback_var = tk.DoubleVar(value=0.0)
        self.vel_var = tk.DoubleVar(value=10.0)
        self.acc_var = tk.DoubleVar(value=100.0)
        self.dec_var = tk.DoubleVar(value=100.0)
        self.jerk_var = tk.DoubleVar(value=1000.0)

        self.power_state = False
        self.power_feedback = tk.BooleanVar(value=False)

        self.stop_thread = threading.Event()
        self.time_buf = deque(maxlen=200)
        self.pos_buf = deque(maxlen=200)
        self.buf_lock = threading.Lock()
        self.t0 = time.time()

        self._create_widgets()
        self._init_plot()
        self._start_plot_timer()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # -------------------------------------------------------------------------
    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Connection frame ---
        conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding=10)
        conn_frame.pack(fill=tk.X)
        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, padx=5, sticky=tk.W)
        ttk.Entry(conn_frame, textvariable=self.host_var, width=15).grid(row=0, column=1, padx=5)
        ttk.Label(conn_frame, text="Port:").grid(row=0, column=2, padx=5, sticky=tk.W)
        ttk.Entry(conn_frame, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=5)
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self._toggle_connection)
        self.connect_btn.grid(row=0, column=4, padx=5)

        # --- Power / Execute frame ---
        power_frame = ttk.LabelFrame(main_frame, text="Power / Execute", padding=10)
        power_frame.pack(fill=tk.X, pady=(10, 5))

        self.power_btn = ttk.Button(power_frame, text="Power OFF", command=self._toggle_power)
        self.power_btn.grid(row=0, column=0, padx=5, pady=2)

        self.power_led = tk.Canvas(power_frame, width=20, height=20,
                                   highlightthickness=1, highlightbackground="gray")
        self.power_led.grid(row=0, column=1, padx=10, pady=2)
        self._update_led(self.power_feedback.get())

        self.execute_btn = ttk.Button(power_frame, text="Execute")
        self.execute_btn.grid(row=0, column=2, padx=10, pady=2)
        self.execute_btn.bind("<ButtonPress>", lambda e: self._execute_press())
        self.execute_btn.bind("<ButtonRelease>", lambda e: self._execute_release())

        # --- Home / Save / EEPROM frame ---
        home_frame = ttk.LabelFrame(main_frame, text="Home & Save Controls", padding=10)
        home_frame.pack(fill=tk.X, pady=(5, 10))

        self._add_bool_button(home_frame, "Home Mode Geç", 3, 0)
        self._add_bool_button(home_frame, "Start Home", 4, 1)
        self._add_bool_button(home_frame, "Save", 5, 2)
        self._add_bool_button(home_frame, "Write EEPROM", 6, 3)

        # --- Jog Controls Frame ---
        jog_frame = ttk.LabelFrame(main_frame, text="Jog Controls", padding=10)
        jog_frame.pack(fill=tk.X, pady=(5, 10))

        self._add_bool_button(jog_frame, "Jog Mode", 7, 0)
        self._add_bool_button(jog_frame, "Jog Forward", 8, 1)
        self._add_bool_button(jog_frame, "Jog Backward", 9, 2)

        # --- Position / Params frame ---
        pos_frame = ttk.LabelFrame(main_frame, text="Motion Parameters", padding=10)
        pos_frame.pack(fill=tk.X, pady=(5, 10))

        ttk.Label(pos_frame, text="Target Pos (mm):").grid(row=0, column=0, padx=5, sticky=tk.W)
        ttk.Entry(pos_frame, textvariable=self.position_var, width=10).grid(row=0, column=1, padx=5)
        ttk.Button(pos_frame, text="Write Pos", command=self._write_position).grid(row=0, column=2, padx=5)

        ttk.Label(pos_frame, text="Vel (mm/s):").grid(row=1, column=0, padx=5, sticky=tk.W)
        ttk.Entry(pos_frame, textvariable=self.vel_var, width=10).grid(row=1, column=1, padx=5)
        ttk.Label(pos_frame, text="Acc (mm²/s):").grid(row=2, column=0, padx=5, sticky=tk.W)
        ttk.Entry(pos_frame, textvariable=self.acc_var, width=10).grid(row=2, column=1, padx=5)
        ttk.Label(pos_frame, text="Dec (mm²/s):").grid(row=3, column=0, padx=5, sticky=tk.W)
        ttk.Entry(pos_frame, textvariable=self.dec_var, width=10).grid(row=3, column=1, padx=5)
        ttk.Label(pos_frame, text="Jerk (mm³/s):").grid(row=4, column=0, padx=5, sticky=tk.W)
        ttk.Entry(pos_frame, textvariable=self.jerk_var, width=10).grid(row=4, column=1, padx=5)

        ttk.Button(pos_frame, text="Write Params", command=self._write_motion_params).grid(
            row=5, column=0, columnspan=3, pady=5
        )

        ttk.Label(pos_frame, text="Feedback Pos:").grid(row=6, column=0, padx=5, sticky=tk.W)
        ttk.Label(pos_frame, textvariable=self.feedback_var, width=12).grid(row=6, column=1, padx=5, sticky=tk.W)

        # --- Plot frame ---
        self.plot_frame = ttk.LabelFrame(main_frame, text="Live Plot", padding=6)
        self.plot_frame.pack(fill=tk.BOTH, expand=True)

        # --- Status bar ---
        status_bar = ttk.Label(self.root, textvariable=self.status_var,
                               relief=tk.SUNKEN, anchor=tk.W, padding=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self._update_ui_state()

    # -------------------------------------------------------------------------
    def _add_bool_button(self, parent, text, addr, column):
        btn = ttk.Button(parent, text=text)
        btn.grid(row=0, column=column, padx=10, pady=5)
        btn.bind("<ButtonPress>", lambda e: self._set_bool_press(addr, text))
        btn.bind("<ButtonRelease>", lambda e: self._set_bool_release(addr, text))
        setattr(self, f"btn_{addr}", btn)

    def _set_bool_press(self, addr, name):
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_bool_value(addr, True)
            self.status_var.set(f"▶ {name} (Addr {addr}) = True")
        except Exception as e:
            self.status_var.set(f"{name} press error: {e}")

    def _set_bool_release(self, addr, name):
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_bool_value(addr, False)
            self.status_var.set(f"⏹ {name} (Addr {addr}) = False")
        except Exception as e:
            self.status_var.set(f"{name} release error: {e}")

    # -------------------------------------------------------------------------
    def _init_plot(self):
        self.fig = Figure(figsize=(6.5, 3.0), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Position (mm)")
        self.ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        self.line, = self.ax.plot([], [], linewidth=1.5, color='blue')
        self.ax.set_xlim(0, 5)
        self.ax.set_ylim(-1, 1)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=tk.BOTH, expand=True)

    def _start_plot_timer(self):
        self._update_plot()
        self.root.after(100, self._start_plot_timer)

    def _update_plot(self):
        with self.buf_lock:
            if len(self.time_buf) < 2:
                return
            x, y = list(self.time_buf), list(self.pos_buf)
        self.line.set_data(x, y)
        self.ax.set_xlim(x[0], x[-1])
        ymin, ymax = min(y), max(y)
        pad = max((ymax - ymin) * 0.1, 0.1)
        self.ax.set_ylim(ymin - pad, ymax + pad)
        self.canvas.draw_idle()

    # -------------------------------------------------------------------------
    def _update_led(self, state):
        self.power_led.delete("all")
        color = "green" if state else "red"
        self.power_led.create_oval(2, 2, 18, 18, fill=color)

    def _toggle_power(self):
        if not self.is_connected or not self.client:
            return
        try:
            self.power_state = not self.power_state
            self.client.set_bool_value(0, self.power_state)
            self.power_btn.config(text="Power ON" if not self.power_state else "Power OFF")
            self.status_var.set(f"⚡ Power {'ON' if self.power_state else 'OFF'} (Addr 0)")
        except Exception as e:
            messagebox.showerror("Send Error", str(e))

    def _execute_press(self):
        if self.client and self.is_connected:
            self.client.set_bool_value(1, True)
            self.status_var.set("▶ Execute = True")

    def _execute_release(self):
        if self.client and self.is_connected:
            self.client.set_bool_value(1, False)
            self.status_var.set("⏹ Execute = False")

    # -------------------------------------------------------------------------
    def _write_position(self):
        if not self.client or not self.is_connected:
            return
        val = float(self.position_var.get())
        self.client.set_lword_value(1, val)
        self.status_var.set(f"✅ Position {val:.2f} written (Addr 1)")

    def _write_motion_params(self):
        if not self.client or not self.is_connected:
            return
        try:
            self.client.set_lword_value(2, float(self.vel_var.get()))
            self.client.set_lword_value(3, float(self.acc_var.get()))
            self.client.set_lword_value(4, float(self.dec_var.get()))
            self.client.set_lword_value(5, float(self.jerk_var.get()))
            self.status_var.set("✅ Motion params sent to 2–5")
        except Exception as e:
            messagebox.showerror("Send Error", str(e))

    # -------------------------------------------------------------------------
    def _toggle_connection(self):
        if self.is_connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        host, port = self.host_var.get(), int(self.port_var.get())
        try:
            self.client = Client()
            self.client.connect(host, port)
            self.is_connected = True
            self.status_var.set(f"✅ Connected to {host}:{port}")
            with self.buf_lock:
                self.time_buf.clear()
                self.pos_buf.clear()
            self.t0 = time.time()
            self._write_motion_params()
            self._start_feedback_thread()
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))
            self.is_connected = False
        self._update_ui_state()

    def _disconnect(self):
        self.is_connected = False
        self.stop_thread.set()
        if self.client:
            self.client.disconnect()
            self.client = None
        self.status_var.set("🔌 Disconnected")
        self._update_ui_state()

    # -------------------------------------------------------------------------
    def _start_feedback_thread(self):
        if hasattr(self, "feedback_thread") and self.feedback_thread.is_alive():
            return
        self.stop_thread.clear()
        threading.Thread(target=self._feedback_loop, daemon=True).start()

    def _feedback_loop(self):
        while not self.stop_thread.is_set():
            if self.client and self.is_connected:
                try:
                    pwr_fb = self.client.get_bool_value(80)
                    raw_val = self.client.get_lword_value(100)
                    pos = struct.unpack('d', struct.pack('Q', raw_val))[0]
                    t = time.time() - self.t0
                    with self.buf_lock:
                        self.time_buf.append(t)
                        self.pos_buf.append(pos)
                    self.root.after(0, self.feedback_var.set, round(pos, 3))
                    self.root.after(0, self._update_led, pwr_fb)
                except Exception:
                    pass
            time.sleep(0.1)

    # -------------------------------------------------------------------------
    def _update_ui_state(self):
        state = tk.NORMAL if self.is_connected else tk.DISABLED
        for widget_name in dir(self):
            if widget_name.startswith("btn_"):
                getattr(self, widget_name).config(state=state)
        self.power_btn.config(state=state)
        self.execute_btn.config(state=state)
        self.connect_btn.config(text="Disconnect" if self.is_connected else "Connect")

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