import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os
import sys

# mil_api modülünün yolu
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- Import API Client ---
try:
    from mil_api import Client, ApiError, ConnectionError, SendError
except (ImportError, OSError) as e:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Startup Error",
        "Gerekli API modülü (mil_api.py) veya kütüphanesi yüklenemedi.\n"
        "Dosyaların doğru klasörde olduğundan emin olun.\n\n"
        f"Detaylar: {e}"
    )
    Client = None


class BooleanMonitorApp:
    """Tkinter GUI to continuously monitor specific boolean addresses via MilConnAPI."""

    MONITOR_BOOL_ADDRESSES = {
        "in0": 0, "in1": 1, "in2": 2,
        "out0": 3, "out1": 4, "out2": 5
    }

    TOGGLE_ADDRESSES = ["in0", "in1", "in2"]

    def __init__(self, root):
        self.root = root
        self.root.title("Boolean Adres İzleyici")
        self.root.geometry("600x350")

        self.client: Client | None = None
        self.is_connected = False
        self.host_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="60000")
        self.status_var = tk.StringVar(value="🔌 Bağlantı Kesik")

        # Boolean değişkenler
        self.bool_vars = {name: tk.BooleanVar(value=False)
                          for name in self.MONITOR_BOOL_ADDRESSES.keys()}

        self.toggle_states = {name: False for name in self.TOGGLE_ADDRESSES}

        self.stop_thread = threading.Event()
        self.feedback_thread = None

        self._create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # -------------------------------------------------------------------------
    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Connection frame ---
        conn_frame = ttk.LabelFrame(main_frame, text="Bağlantı", padding=10)
        conn_frame.pack(fill=tk.X)
        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.host_entry = ttk.Entry(conn_frame, textvariable=self.host_var, width=15)
        self.host_entry.grid(row=0, column=1, padx=5)
        ttk.Label(conn_frame, text="Port:").grid(row=0, column=2, padx=5, sticky=tk.W)
        self.port_entry = ttk.Entry(conn_frame, textvariable=self.port_var, width=8)
        self.port_entry.grid(row=0, column=3, padx=5)
        self.connect_btn = ttk.Button(conn_frame, text="Bağlan", command=self._toggle_connection)
        self.connect_btn.grid(row=0, column=4, padx=5)

        # --- Monitor frame ---
        monitor_frame = ttk.LabelFrame(main_frame, text="Boolean Değerler", padding=10)
        monitor_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 5))

        self._setup_monitor_section(monitor_frame, "Girişler (IN)", ["in0", "in1", "in2"], 0, include_toggle=True)
        self._setup_monitor_section(monitor_frame, "Çıkışlar (OUT)", ["out0", "out1", "out2"], 1, include_toggle=False)

        # --- Status bar ---
        status_bar = ttk.Label(self.root, textvariable=self.status_var,
                               relief=tk.SUNKEN, anchor=tk.W, padding=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self._update_ui_state()

    # -------------------------------------------------------------------------
    def _setup_monitor_section(self, parent_frame, title, names, column_offset, include_toggle=False):
        section_frame = ttk.Frame(parent_frame, padding=5)
        parent_frame.grid_columnconfigure(column_offset, weight=1)
        section_frame.grid(row=0, column=column_offset, padx=10, pady=5, sticky=tk.N + tk.W + tk.E + tk.S)

        ttk.Label(section_frame, text=title, font=("Arial", 10, "bold")).pack(pady=5)

        for i, name in enumerate(names):
            addr = self.MONITOR_BOOL_ADDRESSES[name]
            row_frame = ttk.Frame(section_frame)
            row_frame.pack(fill=tk.X, pady=2)

            ttk.Label(row_frame, text=f"{name} (Addr {addr}):").pack(side=tk.LEFT, padx=5)

            led_canvas = tk.Canvas(row_frame, width=20, height=20,
                                   highlightthickness=1, highlightbackground="gray")
            led_canvas.pack(side=tk.LEFT, padx=10)

            self.bool_vars[name].canvas = led_canvas
            self._update_led_display(led_canvas, self.bool_vars[name].get())

            if include_toggle and name in self.TOGGLE_ADDRESSES:
                toggle_btn = ttk.Button(row_frame, text="Yaz/Oku Değ. (Toggle)",
                                        command=lambda n=name: self._toggle_bool_value(n))
                toggle_btn.pack(side=tk.LEFT, padx=10)

    # -------------------------------------------------------------------------
    def _update_led_display(self, canvas, state):
        canvas.delete("all")
        color = "green" if state else "red"
        canvas.create_oval(2, 2, 18, 18, fill=color)

    # -------------------------------------------------------------------------
    def _toggle_bool_value(self, name):
        if not self.is_connected or not self.client:
            messagebox.showerror("Hata", "Önce API'ye bağlanın.")
            return

        addr = self.MONITOR_BOOL_ADDRESSES.get(name)
        if addr is None:
            messagebox.showerror("Hata", f"'{name}' için adres bulunamadı.")
            return

        new_value = not self.bool_vars[name].get()
        value_to_write = 1 if new_value else 0

        try:
            self.client.set_bool_value(addr, value_to_write)
            self.status_var.set(f"✅ Adres {addr} ({name}) değeri: {value_to_write} olarak ayarlandı.")
        except Exception as e:
            messagebox.showerror("Yazma Hatası", f"Adres {addr} ({name}) yazılırken hata: {str(e)}")
            self.status_var.set(f"❌ Yazma Hatası: {name}")

    # -------------------------------------------------------------------------
    def _toggle_connection(self):
        if self.is_connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        if Client is None:
            messagebox.showerror("Hata", "API istemcisi yüklenemedi. Bağlanılamıyor.")
            return

        host, port = self.host_var.get(), int(self.port_var.get())
        try:
            self.client = Client()
            self.client.connect(host, port)
            self.is_connected = True
            self.status_var.set(f"✅ Bağlandı: {host}:{port}")
            self._start_feedback_thread()
        except Exception as e:
            messagebox.showerror("Bağlantı Hatası", str(e))
            self.is_connected = False
        self._update_ui_state()

    def _disconnect(self):
        self.is_connected = False
        self.stop_thread.set()

        if self.feedback_thread and self.feedback_thread.is_alive():
            self.feedback_thread.join(timeout=0.5)

        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
            self.client = None

        self.status_var.set("🔌 Bağlantı Kesik")
        self._update_ui_state()

    # -------------------------------------------------------------------------
    def _start_feedback_thread(self):
        if self.feedback_thread and self.feedback_thread.is_alive():
            return
        self.stop_thread.clear()
        self.feedback_thread = threading.Thread(target=self._feedback_loop, daemon=True)
        self.feedback_thread.start()

    def _feedback_loop(self):
        while not self.stop_thread.is_set():
            if self.client and self.is_connected:
                try:
                    updates = {}
                    for name, addr in self.MONITOR_BOOL_ADDRESSES.items():
                        value = self.client.get_bool_value(addr)
                        updates[name] = value

                    self.root.after(0, self._update_monitor_ui, updates)
                except Exception as e:
                    self.root.after(0, self._handle_feedback_error, str(e))
                    break
            time.sleep(0.1)

    def _update_monitor_ui(self, updates):
        for name, value in updates.items():
            current_value = self.bool_vars[name].get()
            if current_value != value:
                self.bool_vars[name].set(value)
                canvas = self.bool_vars[name].canvas
                self._update_led_display(canvas, value)

        self.status_var.set(f"🔄 Boolean değerler güncellendi.")

    def _handle_feedback_error(self, error_message):
        messagebox.showerror("API Okuma Hatası", f"Veri okuma hatası oluştu: {error_message}")
        self._disconnect()

    # -------------------------------------------------------------------------
    def _update_ui_state(self):
        self.connect_btn.config(text="Bağlantıyı Kes" if self.is_connected else "Bağlan")

        entry_state = tk.DISABLED if self.is_connected else tk.NORMAL
        self.host_entry.config(state=entry_state)
        self.port_entry.config(state=entry_state)

    def _on_closing(self):
        self._disconnect()
        self.root.destroy()


# -------------------------------------------------------------------------
if __name__ == "__main__":
    if Client:
        root = tk.Tk()
        app = BooleanMonitorApp(root)
        root.mainloop()
    else:
        print("--- GUI API yükleme hatası nedeniyle başlatılamadı. ---")
