import tkinter as tk
from tkinter import ttk, messagebox
import os
import sys
import time

# mil_api yolu
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from mil_api import Client
except Exception as e:
    Client = None
    raise e


# ---------------- BOOL ADRESLER ----------------
BOOL_ADDR = {
    "pos": 136,     # Buton konumu yaz
    "linear": 137,  # Lineer kaynak
    "osc": 138,     # Osilasyon kaynak
    "undo": 139     # Geri
}


class WeldingRemoteControl:

    def __init__(self, root):
        self.root = root
        self.root.title("Welding Remote Control")
        self.root.geometry("420x320")

        self.client = None
        self.connected = False

        # Toggle durumları
        self.linear_active = False
        self.osc_active = False

        # Undo stack
        self.action_stack = []

        # UI değişkenleri
        self.host_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="60000")
        self.status_var = tk.StringVar(value="🔌 Bağlantı Yok")

        self._create_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- UI ----------------
    def _create_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # ---- Connection ----
        conn = ttk.LabelFrame(main, text="Server Bağlantı", padding=10)
        conn.pack(fill=tk.X)

        ttk.Label(conn, text="Host").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(conn, textvariable=self.host_var, width=15).grid(row=0, column=1)

        ttk.Label(conn, text="Port").grid(row=0, column=2, padx=(10, 0))
        ttk.Entry(conn, textvariable=self.port_var, width=8).grid(row=0, column=3)

        ttk.Button(conn, text="Bağlan / Kes", command=self._toggle_connection)\
            .grid(row=0, column=4, padx=10)

        # ---- Buttons ----
        ctrl = ttk.LabelFrame(main, text="Kontroller", padding=10)
        ctrl.pack(fill=tk.BOTH, expand=True, pady=10)

        self._momentary_button(ctrl, "Buton Konumu Yaz", self._pos_action).pack(fill=tk.X, pady=4)
        self._momentary_button(ctrl, "Lineer Kaynak Başlat / Bitir", self._linear_action).pack(fill=tk.X, pady=4)
        self._momentary_button(ctrl, "Osilasyon Kaynak Başlat / Bitir", self._osc_action).pack(fill=tk.X, pady=4)
        self._momentary_button(ctrl, "Geri (Undo)", self._undo_action).pack(fill=tk.X, pady=4)

        ttk.Label(self.root, textvariable=self.status_var,
                  relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM)

    # ---------------- BUTTON HELPER ----------------
    def _momentary_button(self, parent, text, action):
        btn = ttk.Button(parent, text=text)
        btn.bind("<ButtonPress-1>", lambda e: action(True))
        btn.bind("<ButtonRelease-1>", lambda e: action(False))
        return btn

    # ---------------- ACTIONS ----------------
    def _pos_action(self, state):
        self._write_bool("pos", state)
        if state:
            self.status_var.set(f"📍 Buton basıldı ({time.strftime('%H:%M:%S')})")

    def _linear_action(self, state):
        if state:
            self.linear_active = not self.linear_active
            self.action_stack.append(("linear", self.linear_active))
            self.status_var.set(
                "▶ Lineer Kaynak AKTİF" if self.linear_active else "■ Lineer Kaynak PASİF"
            )
        self._write_bool("linear", state)

    def _osc_action(self, state):
        if state:
            self.osc_active = not self.osc_active
            self.action_stack.append(("osc", self.osc_active))
            self.status_var.set(
                "▶ Osilasyon Kaynak AKTİF" if self.osc_active else "■ Osilasyon Kaynak PASİF"
            )
        self._write_bool("osc", state)

    def _undo_action(self, state):
        if state and self.action_stack:
            name, _ = self.action_stack.pop()
            self._write_bool(name, False)
            self.status_var.set(f"↩ Geri alındı: {name}")

        self._write_bool("undo", state)

    # ---------------- API ----------------
    def _write_bool(self, name, value):
        if not self.connected or not self.client:
            return
        try:
            self.client.set_bool_value(BOOL_ADDR[name], bool(value))
        except Exception as e:
            messagebox.showerror("API Hatası", str(e))

    # ---------------- CONNECTION ----------------
    def _toggle_connection(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        if Client is None:
            messagebox.showerror("Hata", "API yüklenemedi")
            return
        try:
            self.client = Client()
            self.client.connect(self.host_var.get(), int(self.port_var.get()))
            self.connected = True
            self.status_var.set("✅ Server'a bağlandı")
        except Exception as e:
            messagebox.showerror("Bağlantı Hatası", str(e))

    def _disconnect(self):
        try:
            if self.client:
                self.client.disconnect()
        except Exception:
            pass
        self.client = None
        self.connected = False
        self.status_var.set("🔌 Bağlantı Kesildi")

    # ---------------- CLOSE ----------------
    def _on_close(self):
        self._disconnect()
        self.root.destroy()


# ---------------- MAIN ----------------
if __name__ == "__main__":
    root = tk.Tk()
    app = WeldingRemoteControl(root)
    root.mainloop()
