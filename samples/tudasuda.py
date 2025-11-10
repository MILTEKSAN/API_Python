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
    """Tkinter GUI to write target position and motion parameters (vel, acc, dec, jerk),
    monitor feedback, and show live position graph."""

    def __init__(self, root):
        self.root = root
        self.root.title("MilConnAPI Controls")
        self.root.geometry("720x800")

        self.client: Client | None = None
        self.is_connected = False
        self.host_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="60000")
        self.status_var = tk.StringVar(value="🔌 Disconnected")

        # Motion parameter variables
        self.position_var = tk.DoubleVar(value=0.0)
        self.feedback_var = tk.DoubleVar(value=0.0)
        self.vel_var = tk.DoubleVar(value=10.0)
        self.acc_var = tk.DoubleVar(value=100.0)
        self.dec_var = tk.DoubleVar(value=100.0)
        self.jerk_var = tk.DoubleVar(value=1000.0)

        # Power state
        self.power_state = False
        self.power_feedback = tk.BooleanVar(value=False)

        # Thread control
        self.stop_thread = threading.Event()

        # Plot buffers
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

        # ------------------- TOP: Connection + POWER SIDE BY SIDE -------------------
        top = ttk.Frame(main_frame)
        top.pack(fill=tk.X, pady=(0, 10))

        # Connection
        conn_frame = ttk.LabelFrame(top, text="Connection", padding=10)
        conn_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(conn_frame, textvariable=self.host_var, width=14).grid(row=0, column=1, padx=4)

        ttk.Label(conn_frame, text="Port:").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(conn_frame, textvariable=self.port_var, width=7).grid(row=0, column=3, padx=4)

        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self._toggle_connection)
        self.connect_btn.grid(row=0, column=4, padx=6)

        # POWER BUTTON + LED
        power_frame = ttk.Frame(top)
        power_frame.pack(side=tk.LEFT, padx=20)

        self.power_btn = ttk.Button(power_frame, text="Power OFF", command=self._toggle_power)
        self.power_btn.pack(side=tk.LEFT)

        self.power_led = tk.Canvas(power_frame, width=20, height=20,
                                   highlightthickness=1, highlightbackground="gray")
        self.power_led.pack(side=tk.LEFT, padx=8)
        self._update_led(False)


        # =============================================================
        # SECOND ROW: 3 COLUMNS (Params / Position / Execute)
        # =============================================================

        second_row = ttk.Frame(main_frame)
        second_row.pack(fill=tk.X, pady=10)

        # --------- Column 1 → MOTION PARAMS -----------
        params_frame = ttk.LabelFrame(second_row, text="Motion Params", padding=10)
        params_frame.pack(side=tk.LEFT, fill=tk.Y, expand=True, padx=5)

        self.axis_var = tk.IntVar(value=1)
        ttk.Label(params_frame, text="Axis:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.axis_var, width=6).grid(row=0, column=1)

        ttk.Label(params_frame, text="Vel:").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.vel_var, width=8).grid(row=1, column=1)

        ttk.Label(params_frame, text="Acc:").grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.acc_var, width=8).grid(row=2, column=1)

        ttk.Label(params_frame, text="Dec:").grid(row=3, column=0, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.dec_var, width=8).grid(row=3, column=1)

        ttk.Label(params_frame, text="Jerk:").grid(row=4, column=0, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.jerk_var, width=8).grid(row=4, column=1)

        ttk.Button(params_frame, text="Write Params", command=self._write_motion_params)\
            .grid(row=5, column=0, columnspan=2, pady=5)


        # --------- Column 2 → POSITION -----------
        pos_frame = ttk.LabelFrame(second_row, text="Position", padding=10)
        pos_frame.pack(side=tk.LEFT, fill=tk.Y, expand=True, padx=5)

        ttk.Label(pos_frame, text="Target (mm):").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(pos_frame, textvariable=self.position_var, width=8).grid(row=0, column=1, padx=5)

        ttk.Button(pos_frame, text="Write Position", command=self._write_position)\
            .grid(row=1, column=0, columnspan=2, pady=5)


        # --------- Column 3 → EXECUTE -----------
        exec_frame = ttk.LabelFrame(second_row, text="Execute", padding=10)
        exec_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # Existing Execute (Hold)
        self.execute_btn = ttk.Button(exec_frame, text="Execute (Hold)")
        self.execute_btn.pack(pady=5)
        self.execute_btn.bind("<ButtonPress>", lambda e: self._execute_press())
        self.execute_btn.bind("<ButtonRelease>", lambda e: self._execute_release())

        # ✅ NEW: Velocity Forward (Hold)
        self.exec_vel_fwd_btn = ttk.Button(exec_frame, text="Vel Forward")
        self.exec_vel_fwd_btn.pack(pady=5)
        self.exec_vel_fwd_btn.bind("<ButtonPress>", lambda e: self._vel_forward_press())
        self.exec_vel_fwd_btn.bind("<ButtonRelease>", lambda e: self._vel_forward_release())

        # ✅ NEW: Velocity Backward (Hold)
        self.exec_vel_bwd_btn = ttk.Button(exec_frame, text="Vel Backward")
        self.exec_vel_bwd_btn.pack(pady=5)
        self.exec_vel_bwd_btn.bind("<ButtonPress>", lambda e: self._vel_backward_press())
        self.exec_vel_bwd_btn.bind("<ButtonRelease>", lambda e: self._vel_backward_release())

        # ✅ NEW: Halt (Single Click)
        self.exec_halt_btn = ttk.Button(exec_frame, text="HALT")
        self.exec_halt_btn.pack(pady=5)
        self.exec_halt_btn.config(command=self._execute_halt)

        # --------- Feedback below second row ----------
        feedback_frame = ttk.Frame(main_frame)
        feedback_frame.pack(fill=tk.X, pady=5)

        ttk.Label(feedback_frame, text="Feedback Pos:").pack(side=tk.LEFT)
        ttk.Label(feedback_frame, textvariable=self.feedback_var).pack(side=tk.LEFT, padx=10)


        # --------- PLOT FRAME BELOW EVERYTHING ----------
        self.plot_frame = ttk.LabelFrame(main_frame, text="Live Plot", padding=6)
        self.plot_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 10))

        # Status Bar
        status_bar = ttk.Label(self.root, textvariable=self.status_var,
                               relief=tk.SUNKEN, anchor=tk.W, padding=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self._update_ui_state()


    # -------------------------------------------------------------------------
    def _init_plot(self):
        """Initialize matplotlib Figure and Line inside Tk."""
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
        """Periodic GUI update for the plot."""
        self._update_plot()
        self.root.after(100, self._start_plot_timer)

    def _update_plot(self):
        """Refresh the live plot."""
        with self.buf_lock:
            if len(self.time_buf) < 2:
                return
            x = list(self.time_buf)
            y = list(self.pos_buf)

        self.line.set_data(x, y)
        self.ax.set_xlim(x[0], x[-1])
        ymin, ymax = min(y), max(y)
        pad = max((ymax - ymin) * 0.1, 0.1)
        self.ax.set_ylim(ymin - pad, ymax + pad)
        self.canvas.draw_idle()

    # -------------------------------------------------------------------------
    def _update_led(self, state: bool):
        self.power_led.delete("all")
        color = "green" if state else "red"
        self.power_led.create_oval(2, 2, 18, 18, fill=color)

    # -------------------------------------------------------------------------
    def _write_position(self):
        """Send position to address 1."""
        if not self.is_connected or not self.client:
            messagebox.showwarning("Not Connected", "Connect first.")
            return
        try:
            value = float(self.position_var.get())
            self.client.set_lword_value(1, value)
            self.status_var.set(f"✅ Position {value:.3f} written to Addr 1")
        except Exception as e:
            messagebox.showerror("Send Error", f"Failed to write position.\n\n{e}")

    def _write_motion_params(self):
        """Send velocity, acc, dec, jerk as LWORDs to 2,3,4,5."""
        if not self.is_connected or not self.client:
            messagebox.showwarning("Not Connected", "Connect first.")
            return
        try:
            self.client.set_byte_value(0, int(self.axis_var.get()))
            self.client.set_lword_value(2, float(self.vel_var.get()))
            self.client.set_lword_value(3, float(self.acc_var.get()))
            self.client.set_lword_value(4, float(self.dec_var.get()))
            self.client.set_lword_value(5, float(self.jerk_var.get()))
            self.status_var.set("✅ Motion params sent to 2,3,4,5")
        except Exception as e:
            messagebox.showerror("Send Error", f"Failed to send motion params.\n\n{e}")
            
    # --------- Velocity Forward (addr 7) ----------
    def _vel_forward_press(self):
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_bool_value(7, True)
            self.status_var.set("▶ Vel Forward = True (Pressed)")
        except Exception as e:
            self.status_var.set(f"Vel Forward press error: {e}")

    def _vel_forward_release(self):
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_bool_value(7, False)
            self.status_var.set("⏹ Vel Forward = False (Released)")
        except Exception as e:
            self.status_var.set(f"Vel Forward release error: {e}")


    # --------- Velocity Backward (addr 8) ----------
    def _vel_backward_press(self):
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_bool_value(8, True)
            self.status_var.set("▶ Vel Backward = True (Pressed)")
        except Exception as e:
            self.status_var.set(f"Vel Backward press error: {e}")

    def _vel_backward_release(self):
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_bool_value(8, False)
            self.status_var.set("⏹ Vel Backward = False (Released)")
        except Exception as e:
            self.status_var.set(f"Vel Backward release error: {e}")


    # --------- HALT (addr 9, one-shot) ----------
    def _execute_halt(self):
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_bool_value(9, True)
            time.sleep(0.1)
            self.client.set_bool_value(9, False)
            self.status_var.set("⛔ HALT triggered (pulse on addr 9)")
        except Exception as e:
            self.status_var.set(f"Halt error: {e}")

    # -------------------------------------------------------------------------
    def _toggle_power(self):
        if not self.is_connected or not self.client:
            messagebox.showwarning("Not Connected", "Connect first.")
            return
        try:
            self.power_state = not self.power_state
            self.client.set_bool_value(0, self.power_state)
            self.power_btn.config(text="Power ON" if not self.power_state else "Power OFF")
            self.status_var.set(f"⚡ Power {'ON' if self.power_state else 'OFF'} sent to Addr 0")
        except Exception as e:
            messagebox.showerror("Send Error", str(e))

    def _execute_press(self):
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_bool_value(1, True)
            self.status_var.set("▶ Execute = True (Pressed)")
        except Exception as e:
            self.status_var.set(f"Execute press error: {e}")

    def _execute_release(self):
        if not self.is_connected or not self.client:
            return
        try:
            self.client.set_bool_value(1, False)
            self.status_var.set("⏹ Execute = False (Released)")
        except Exception as e:
            self.status_var.set(f"Execute release error: {e}")

    # -------------------------------------------------------------------------
    def _start_feedback_thread(self):
        if hasattr(self, "feedback_thread") and self.feedback_thread.is_alive():
            return
        self.stop_thread.clear()
        self.feedback_thread = threading.Thread(target=self._feedback_loop, daemon=True)
        self.feedback_thread.start()

    def _feedback_loop(self):
        """Read position feedback depending on selected axis."""
        while not self.stop_thread.is_set():
            if self.is_connected and self.client:
                try:
                    axis = int(self.axis_var.get())

                    # Position address = 100 + axis
                    pos_address = 100 + axis  

                    raw_val = self.client.get_lword_value(pos_address)
                    pos = struct.unpack('d', struct.pack('Q', raw_val))[0]
                    formatted_pos = round(pos, 3)

                    t = time.time() - self.t0
                    with self.buf_lock:
                        self.time_buf.append(t)
                        self.pos_buf.append(formatted_pos)

                    # Update GUI safely
                    self.root.after(0, self.feedback_var.set, formatted_pos)

                    # Power status still on bool 80
                    power_fb = self.client.get_bool_value(80)
                    self.root.after(0, self._update_led, power_fb)

                except Exception as e:
                    self.root.after(0, self.status_var.set, f"Feedback error: {e}")

            time.sleep(0.1)

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

            # Reset buffers
            with self.buf_lock:
                self.time_buf.clear()
                self.pos_buf.clear()
            self.t0 = time.time()

            # Send default parameters immediately
            self._write_motion_params()

            # Start reading feedback
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
        self.exec_vel_fwd_btn.config(state=state)
        self.exec_vel_bwd_btn.config(state=state)
        self.exec_halt_btn.config(state=state)
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
