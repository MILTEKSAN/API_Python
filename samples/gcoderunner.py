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
        "Failed to load the required API module.\n"
        f"Details: {e}"
    )
    Client = None


# ======================================================================
#                       LINE NUMBERED EDITOR CLASS
# ======================================================================
class LineNumberedEditor(ttk.Frame):
    """A text editor widget with line numbers + file operations."""

    def __init__(self, parent):
        super().__init__(parent)

        # --- Line number pane ---
        self.line_numbers = tk.Text(self, width=5, padx=4, takefocus=0,
                                    border=0, background="#e6e6e6", state="disabled",
                                    font=("Consolas", 12))
        self.line_numbers.pack(side="left", fill="y")

        # --- Main text widget ---
        self.text = tk.Text(self, wrap="none", font=("Consolas", 12), undo=True)
        self.text.pack(side="left", fill="both", expand=True)

        # Scrollbars
        yscroll = ttk.Scrollbar(self, command=self._scroll_y)
        yscroll.pack(side="right", fill="y")
        xscroll = ttk.Scrollbar(self, command=self._scroll_x, orient="horizontal")
        xscroll.pack(side="bottom", fill="x")

        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        # Bind events
        self.text.bind("<KeyRelease>", self._update_line_numbers)
        self.text.bind("<MouseWheel>", lambda e: self._update_line_numbers())
        self.text.bind("<ButtonRelease-1>", lambda e: self._update_line_numbers())

        # Keyboard shortcuts
        self.text.bind("<Control-s>", self._save_as)
        self.text.bind("<Control-o>", self._open_file)
        self.text.bind("<Control-n>", self._new_file)

        # Track file
        self.current_file = None

    # ---------------- Line numbering ----------------
    def _update_line_numbers(self, event=None):
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", tk.END)

        total_lines = int(self.text.index("end-1c").split(".")[0])
        numbers = "\n".join(str(i) for i in range(1, total_lines + 1))

        self.line_numbers.insert("1.0", numbers)
        self.line_numbers.config(state="disabled")

    # Scroll sync
    def _scroll_y(self, *args):
        self.text.yview(*args)
        self.line_numbers.yview(*args)

    def _scroll_x(self, *args):
        self.text.xview(*args)

    # ---------------- File operations ----------------
    def _open_file(self, event=None):
        path = filedialog.askopenfilename(
            filetypes=[("G-Code Files", "*.nc *.gcode *.txt"), ("All Files", "*.*")]
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", content)
            self.current_file = path
            self._update_line_numbers()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _save_as(self, event=None):
        path = filedialog.asksaveasfilename(
            defaultextension=".nc",
            filetypes=[("G-Code Files", "*.nc *.gcode *.txt"), ("All Files", "*.*")]
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text.get("1.0", tk.END))
            self.current_file = path
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _new_file(self, event=None):
        if messagebox.askyesno("Clear", "Clear current editor?"):
            self.text.delete("1.0", tk.END)
            self.current_file = None
            self._update_line_numbers()

    # Public API for external use
    def get_text(self):
        return self.text.get("1.0", tk.END)

    def set_text(self, content: str):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)
        self._update_line_numbers()


# ======================================================================
#                   MAIN MILTEKSAN G-CODE APP
# ======================================================================
class MilteksanGCodeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Milteksan G-Code Loader")
        self.root.geometry("1200x750")

        # Runtime
        self.client: Client | None = None
        self.polling = False
        self.current_line = -1
        self.power_state = False

        # Add these ↓↓↓
        self.single_block_state = False
        self.skip_block_state = False

        # XY buffer
        self.buffer_size = 500
        self.xy_buffer = deque(maxlen=self.buffer_size)

        # Build UI
        self._build_ui()


    # ==================================================================
    #                           UI SETUP
    # ==================================================================
    def _build_ui(self):
        # Connection row
        conn = ttk.Frame(self.root)
        conn.pack(fill="x", padx=10, pady=6)

        ttk.Label(conn, text="IP:").pack(side="left")
        self.ip_entry = ttk.Entry(conn, width=15)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.pack(side="left", padx=4)

        ttk.Label(conn, text="Port:").pack(side="left")
        self.port_entry = ttk.Entry(conn, width=8)
        self.port_entry.insert(0, "60000")
        self.port_entry.pack(side="left", padx=4)

        ttk.Button(conn, text="Connect", command=self.connect_api).pack(side="left", padx=4)
        ttk.Button(conn, text="Disconnect", command=self.disconnect_api).pack(side="left")

        self.status = ttk.Label(conn, text="Disconnected", foreground="red")
        self.status.pack(side="right")

        # Control row
        ctrl = ttk.Frame(self.root)
        ctrl.pack(fill="x", padx=10, pady=5)

        self.power_button = ttk.Button(ctrl, text="Power On", command=self.toggle_power)
        self.power_button.pack(side="left", padx=5)

        ttk.Button(ctrl, text="Save G-Code", command=self.save_gcode).pack(side="left")
        
        # --- Single Block Toggle ---
        self.single_block_button = ttk.Button(
            ctrl,
            text="Single Block: OFF",
            command=self.toggle_single_block
        )
        self.single_block_button.pack(side="left", padx=5)
        # --- Skip Block Toggle ---
        self.skip_block_button = ttk.Button(
            ctrl,
            text="Skip Block: OFF",
            command=self.toggle_skip_block
        )
        self.skip_block_button.pack(side="left", padx=5)
        # Momentary buttons
        self._make_momentary(ctrl, "Load", 2)
        self._make_momentary(ctrl, "Start", 3)
        self._make_momentary(ctrl, "Hold", 4)
        self._make_momentary(ctrl, "Reset", 5)

        self.pos_label = ttk.Label(ctrl, text="X: 0.000  Y: 0.000")
        self.pos_label.pack(side="right")

        # Power LED
        led = ttk.Frame(self.root)
        led.pack(fill="x", padx=10)
        ttk.Label(led, text="Power Status:").pack(side="left")
        self.power_led = tk.Canvas(led, width=20, height=20, highlightthickness=0)
        self.led_circle = self.power_led.create_oval(2, 2, 18, 18, fill="red")
        self.power_led.pack(side="left")

        # Split area
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        # Left: Editor
        left = ttk.Frame(paned)
        paned.add(left, weight=3)

        self.editor = LineNumberedEditor(left)
        self.editor.pack(fill="both", expand=True)
        self.text = self.editor.text

        self.text.tag_configure("running", background="#ffe49c")

        # Right: Plot
        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        self.fig = Figure(figsize=(5, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self._configure_axes()

        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    # ==================================================================
    #                   API CONNECTION / CONTROLS
    # ==================================================================
    def _make_momentary(self, parent, label, addr):
        btn = ttk.Button(parent, text=label)
        btn.pack(side="left", padx=5)
        btn.bind("<ButtonPress-1>", lambda e: self._set_bool(addr, True))
        btn.bind("<ButtonRelease-1>", lambda e: self._set_bool(addr, False))

    def connect_api(self):
        ip = self.ip_entry.get()
        try:
            port = int(self.port_entry.get())
        except:
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
            except:
                pass
        self.status.config(text="Disconnected", foreground="red")

    def toggle_power(self):
        if not self.client or not self.client.is_connected():
            return

        new_state = not self.power_state
        try:
            self.client.set_bool_value(0, new_state)
            self.power_state = new_state
            self.power_button.config(text="Power Off" if new_state else "Power On")
        except:
            pass

    def toggle_single_block(self):
        if not self.client or not self.client.is_connected():
            return

        new_state = not self.single_block_state
        try:
            self.client.set_bool_value(11, new_state)
            self.single_block_state = new_state
            self.single_block_button.config(
                text=f"Single Block: {'ON' if new_state else 'OFF'}"
            )
        except Exception as e:
            print("Single block write error:", e)

    def toggle_skip_block(self):
        if not self.client or not self.client.is_connected():
            return

        new_state = not self.skip_block_state
        try:
            self.client.set_bool_value(12, new_state)   # Address 12
            self.skip_block_state = new_state
            self.skip_block_button.config(
                text=f"Skip Block: {'ON' if new_state else 'OFF'}"
            )
        except Exception as e:
            print("Skip block write error:", e)

    def save_gcode(self):
        save_path = "/home/fehim/NC_Program.txt"
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(self.editor.get_text().strip())
        except Exception as e:
            print("Save error:", e)

    # ==================================================================
    #                          POLLING DATA
    # ==================================================================
    def poll_values(self):
        while self.polling and self.client and self.client.is_connected():
            try:
                line = self.client.get_dword_value(1)

                # XY double
                raw_x = self.client.get_lword_value(100)
                raw_y = self.client.get_lword_value(101)
                x = struct.unpack('<d', struct.pack('<Q', raw_x))[0]
                y = struct.unpack('<d', struct.pack('<Q', raw_y))[0]

                power = self.client.get_bool_value(80)

                self.update_ui(line, x, y, power)
            except:
                pass

            time.sleep(0.2)

    def update_ui(self, line, x, y, power):
        self.root.after(0, lambda: self._update_ui(line, x, y, power))

    def _update_ui(self, line, x, y, power):
        self.pos_label.config(text=f"X: {x:.3f}  Y: {y:.3f}")

        # XY plot buffer
        self.xy_buffer.append((x, y))
        self.draw_xy_path()

        # LED
        self.set_led_state(power)
        if power != self.power_state:
            self.power_state = power
            self.power_button.config(text="Power Off" if power else "Power On")

        # G-code highlight
        if line != self.current_line:
            self.current_line = line
            self.highlight_line(line)

    # ==================================================================
    #                             PLOTTING
    # ==================================================================
    def draw_xy_path(self):
        if len(self.xy_buffer) < 2:
            return

        xs, ys = zip(*self.xy_buffer)

        self._configure_axes()
        self.ax.plot(xs, ys, linewidth=1)
        self.ax.plot(xs[-1], ys[-1], marker="o")

        self.canvas.draw_idle()

    def _configure_axes(self):
        self.ax.clear()
        self.ax.set_title("X-Y Path")
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.grid(True)

    # ==================================================================
    #                             HELPERS
    # ==================================================================
    def set_led_state(self, on):
        color = "lime green" if on else "red"
        self.power_led.itemconfig(self.led_circle, fill=color)

    def highlight_line(self, line_num):
        self.text.tag_remove("running", "1.0", tk.END)
        if line_num <= 0:
            return

        total_lines = int(self.text.index("end-1c").split(".")[0])

        if 1 <= line_num <= total_lines:
            start = f"{line_num}.0"
            end = f"{line_num}.end"
            self.text.tag_add("running", start, end)
            self.text.see(start)

    def _set_bool(self, addr, value):
        try:
            if self.client and self.client.is_connected():
                self.client.set_bool_value(addr, value)
        except:
            pass


# ======================================================================
#                               RUN APP
# ======================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = MilteksanGCodeApp(root)
    root.mainloop()
