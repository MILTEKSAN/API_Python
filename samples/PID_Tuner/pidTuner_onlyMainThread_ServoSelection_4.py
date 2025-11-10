import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import os
import sys
import struct
import threading
import time
from queue import Queue

# mil_api.py dosyasının aynı dizinde olduğunu varsayıyoruz.
# Client sınıfını ve ilgili exception'ları import ediyoruz.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mil_api import Client, ConnectionError, ApiError, SendError

class CNCClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MILTEKSAN TUNE API (Multi-Threaded)")

        try:
            self.client = Client()
        except ApiError as e:
            messagebox.showerror("API Error", f"Failed to initialize the API client: {e}")
            self.root.destroy()
            return
            
        # --- Multi-threading için kilit ve kuyruk ---
        self.lock = threading.Lock()
        self.command_queue = Queue()
        self.worker_thread = threading.Thread(target=self._process_commands, daemon=True)
        self.worker_thread.start()

        # --- UI Değişkenleri ---
        self.ip_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="60000")
        self.write_bool_address_var = tk.StringVar(value="321")
        self.is_connected_var = tk.BooleanVar(value=False)
        self.axis_selection_var = tk.StringVar(value="0")
        self.positive_tune_value_var = tk.StringVar(value="")
        self.negative_tune_value_var = tk.StringVar(value="")
        self.jog_enable_state = False
        self.oscillation_active = False
        self.enable_button_state = tk.BooleanVar(value=False)
        self.servo_driver_var = tk.StringVar()
        self.is_busy = False # UI'da bir işlem devam ediyor mu?

        # --- Okuma/Yazma Değişkenleri ---
        self.read_dword_address_vars = [tk.StringVar(value=str(300 + i)) for i in range(7)]
        self.read_dword_value_vars = [tk.StringVar(value="") for _ in range(7)]
        self.write_dword_address_vars = [tk.StringVar(value=str(340 + i)) for i in range(7)]
        self.write_dword_value_vars = [tk.StringVar(value="0") for _ in range(7)]
        self.axis_value_vars = [tk.StringVar(value="0.000") for _ in range(6)]

        self.write_dword_sliders = []
        self.single_write_buttons = []
        self._slider_update_active = False

        self.create_widgets()

        # Periyodik işlemleri başlat
        self.root.after(500, self.check_connection_status)
        self.root.after(100, self._periodic_position_update) # Ana thread'de çalışmaya devam

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _process_commands(self):
        """
        Arka plandaki iş parçacığı.
        Kuyruktan komutları alır ve işler.
        """
        while True:
            command, args, kwargs = self.command_queue.get()
            try:
                command(*args, **kwargs)
            except Exception as e:
                print(f"ERROR: Command execution failed: {e}")
            finally:
                self.command_queue.task_done()

    def create_widgets(self):
        # UI oluşturma kodları (önceki dosyadakiyle aynı)
        main_frame = tk.Frame(self.root, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.grid_columnconfigure(0, weight=1)

        top_frame = tk.Frame(main_frame)
        top_frame.grid(row=0, column=0, sticky="ew")
        top_frame.grid_columnconfigure(0, weight=0)
        top_frame.grid_columnconfigure(1, weight=1)

        connection_frame = tk.LabelFrame(top_frame, text="Connection", padx=5, pady=5)
        connection_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ns")

        tk.Label(connection_frame, text="Eksen Seçimi (0-7):").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        tk.Entry(connection_frame, textvariable=self.axis_selection_var, width=10).grid(row=0, column=1, padx=5, pady=2, sticky="w")

        self.write_axis_button = tk.Button(connection_frame, text="Write Axis", command=self.on_write_axis_button_press,
                                          bg="lightyellow", activebackground="yellow")
        self.write_axis_button.grid(row=0, column=2, padx=5, pady=2, sticky="ew")
        
        tk.Label(connection_frame, text="Sürücü Tipi:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.servo_driver_combobox = ttk.Combobox(connection_frame, textvariable=self.servo_driver_var, state="readonly", width=15)
        self.servo_driver_combobox['values'] = ("SMB", "Yaskawa", "inovance", "aaaaa", "bbbbbb", "cccccc")
        self.servo_driver_combobox.grid(row=1, column=1, columnspan=2, padx=5, pady=2, sticky="ew")
        self.servo_driver_combobox.bind("<<ComboboxSelected>>", self.on_servo_driver_select)


        tk.Label(connection_frame, text="IP Address:").grid(row=2, column=0, padx=5, pady=2, sticky="w")
        tk.Entry(connection_frame, textvariable=self.ip_var, width=15).grid(row=2, column=1, padx=5, pady=2, sticky="w")

        tk.Label(connection_frame, text="Port:").grid(row=3, column=0, padx=5, pady=2, sticky="w")
        tk.Entry(connection_frame, textvariable=self.port_var, width=15).grid(row=3, column=1, padx=5, pady=2, sticky="w")

        self.connect_button = tk.Button(connection_frame, text="Connect", command=self.toggle_connection)
        self.connect_button.grid(row=4, column=0, pady=5, sticky="ew")

        self.enable_button = tk.Button(connection_frame, text="ENABLE", command=self.toggle_enable,
                                       bg="red", fg="white", activebackground="darkred", activeforeground="white")
        self.enable_button.grid(row=4, column=1, columnspan=2, pady=5, padx=5, sticky="ew")

        self.led_canvas = tk.Canvas(connection_frame, width=20, height=20, bg='gray', highlightthickness=1, relief='sunken')
        self.led_canvas.create_oval(2, 2, 18, 18, fill="red", outline="black", tags="led_oval")
        self.led_canvas.grid(row=2, column=2, rowspan=2, padx=10, pady=5, sticky="ns")

        connection_frame.grid_columnconfigure(0, weight=1)
        connection_frame.grid_columnconfigure(1, weight=1)

        position_frame = tk.LabelFrame(top_frame, text="Position", padx=5, pady=5)
        position_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        axis_labels = [f"axis{i}" for i in range(6)]
        for i, label_text in enumerate(axis_labels):
            tk.Label(position_frame, text=f"{label_text}:", font=("Arial", 9, "bold")).grid(row=i, column=0, padx=5, pady=2, sticky="w")
            tk.Label(position_frame, textvariable=self.axis_value_vars[i], relief="sunken", width=12, anchor="e").grid(row=i, column=1, padx=5, pady=2, sticky="ew")

        position_frame.grid_columnconfigure(1, weight=1)

        pid_frame = tk.LabelFrame(main_frame, text="PID Parameters", padx=5, pady=5)
        pid_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")

        tk.Label(pid_frame, text="Parameters", font=("Arial", 9, "bold")).grid(row=0, column=0, padx=5, pady=2)
        tk.Label(pid_frame, text="Read Adres", font=("Arial", 9, "bold")).grid(row=0, column=1, padx=5, pady=2)
        tk.Label(pid_frame, text="Read Değer", font=("Arial", 9, "bold")).grid(row=0, column=2, padx=5, pady=2)
        tk.Label(pid_frame, text="Write Adres", font=("Arial", 9, "bold")).grid(row=0, column=3, padx=5, pady=2)
        tk.Label(pid_frame, text="Write Değer", font=("Arial", 9, "bold")).grid(row=0, column=4, padx=5, pady=2)
        tk.Label(pid_frame, text="Slider", font=("Arial", 9, "bold")).grid(row=0, column=5, padx=5, pady=2)
        tk.Label(pid_frame, text="Write Single", font=("Arial", 9, "bold")).grid(row=0, column=6, padx=5, pady=2)

        pid_labels = ["Kp_Cur:", "Ki_Cur:", "Kd_Cur:", "Kp_Vel:", "Ki_Vel:", "Kp_Pos:", "Ki_Pos:"]
        single_write_bool_addrs = [10, 11, 12, 13, 14, 16, 17]
        write_buton_label = ["write Kp_cur", "write Ki_cur", "write Kd_cur", "write Kp_vel", "write Ki_vel", "write Kp_pos", "write Ki_pos"]

        for i in range(7):
            tk.Label(pid_frame, text=pid_labels[i]).grid(row=i+1, column=0, padx=5, pady=2, sticky="w")
            tk.Entry(pid_frame, textvariable=self.read_dword_address_vars[i], width=10).grid(row=i+1, column=1, padx=5, pady=2)
            tk.Label(pid_frame, textvariable=self.read_dword_value_vars[i], relief="sunken", width=10, anchor="center").grid(row=i+1, column=2, padx=5, pady=2, sticky="ew")
            tk.Entry(pid_frame, textvariable=self.write_dword_address_vars[i], width=10).grid(row=i+1, column=3, padx=5, pady=2)
            entry = tk.Entry(pid_frame, textvariable=self.write_dword_value_vars[i], width=10)
            entry.grid(row=i+1, column=4, padx=5, pady=2)
            slider = tk.Scale(pid_frame, from_=0, to=1000, orient=tk.HORIZONTAL, showvalue=0, command=lambda val, index=i: self.update_write_value_from_slider(val, index))
            slider.grid(row=i+1, column=5, padx=5, pady=2, sticky="ew")

            bool_addr = single_write_bool_addrs[i]
            btn = tk.Button(pid_frame, text=write_buton_label[i], command=lambda index=i, b_addr=bool_addr: self.on_single_write_press(index, b_addr))
            btn.grid(row=i+1, column=6, padx=2, pady=2, sticky="ew")
            self.single_write_buttons.append(btn)

            self.write_dword_sliders.append(slider)
            self.write_dword_value_vars[i].trace_add("write", lambda *args, index=i: self.update_slider_from_entry(index))
            try:
                slider.set(int(self.write_dword_value_vars[i].get()))
            except ValueError:
                slider.set(0)

        self.read_all_button = tk.Button(pid_frame, text="Read All DWORDS", command=self.on_read_all_press, bg="lightcoral", activebackground="red", font=("Arial", 9, "bold"))
        self.read_all_button.grid(row=8, column=0, columnspan=4, pady=10, sticky="ew")

        self.read_clear_all_button = tk.Button(pid_frame, text="Clear All Values", command=self.clear_read_values, bg="lightgray", activebackground="gray")
        self.read_clear_all_button.grid(row=8, column=4, columnspan=3, pady=10, sticky="ew")

        controls_parent_frame = tk.Frame(main_frame)
        controls_parent_frame.grid(row=2, column=0, sticky="ew")
        controls_parent_frame.grid_columnconfigure(0, weight=1)
        controls_parent_frame.grid_columnconfigure(1, weight=1)

        jog_frame = tk.LabelFrame(controls_parent_frame, text="JOG", padx=5, pady=5)
        jog_frame.grid(row=0, column=0, padx=(5, 2), pady=5, sticky="nsew")

        self.jog_enable_button = tk.Button(jog_frame, text="JOG Enable", bg="orange", activebackground="darkorange", command=self.toggle_jog_enable)
        self.jog_enable_button.grid(row=0, column=0, columnspan=2, pady=5, sticky="ew")

        self.pos_jog_button = tk.Button(jog_frame, text="Positive JOG", bg="lightblue", activebackground="blue")
        self.pos_jog_button.grid(row=1, column=0, pady=5, padx=5, sticky="ew")
        self.pos_jog_button.bind("<ButtonPress-1>", lambda e: self._set_bool_value(323, True))
        self.pos_jog_button.bind("<ButtonRelease-1>", lambda e: self._set_bool_value(323, False))

        self.neg_jog_button = tk.Button(jog_frame, text="Negative JOG", bg="lightblue", activebackground="blue")
        self.neg_jog_button.grid(row=1, column=1, pady=5, padx=5, sticky="ew")
        self.neg_jog_button.bind("<ButtonPress-1>", lambda e: self._set_bool_value(324, True))
        self.neg_jog_button.bind("<ButtonRelease-1>", lambda e: self._set_bool_value(324, False))

        jog_frame.grid_columnconfigure(0, weight=1)
        jog_frame.grid_columnconfigure(1, weight=1)

        tune_frame = tk.LabelFrame(controls_parent_frame, text="Selection Tune Positions", padx=5, pady=5)
        tune_frame.grid(row=0, column=1, padx=(2, 5), pady=5, sticky="nsew")

        self.positive_tune_button = tk.Button(tune_frame, text="Tune Position Selection", bg="lightgreen", activebackground="green")
        self.positive_tune_button.grid(row=0, column=0, pady=5, padx=5, sticky="ew")
        
        self.positive_tune_button.config(command=lambda: self.send_axis_position_to_plc(281, self.positive_tune_value_var))

        tk.Label(tune_frame, textvariable=self.positive_tune_value_var, relief="sunken", width=12).grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.negative_tune_button = tk.Button(tune_frame, text="Negative Tune Position", bg="lightcoral", activebackground="red")
        self.negative_tune_button.grid(row=1, column=0, pady=5, padx=5, sticky="ew")

        self.negative_tune_button.config(command=lambda: self.send_axis_position_to_plc(282, self.negative_tune_value_var))

        tk.Label(tune_frame, textvariable=self.negative_tune_value_var, relief="sunken", width=12).grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        self.oscillation_button = tk.Button(tune_frame, text="START Oscillation Move",
                                            bg="lightyellow", activebackground="yellow",
                                            command=self.toggle_oscillation)
        self.oscillation_button.grid(row=2, column=0, columnspan=2, pady=(10, 5), padx=5, sticky="ew")

        tune_frame.grid_columnconfigure(0, weight=1)
        tune_frame.grid_columnconfigure(1, weight=1)

        pid_frame.grid_columnconfigure(5, weight=2)
        pid_frame.grid_columnconfigure(6, weight=1)

    def on_servo_driver_select(self, event=None):
        """Servo sürücü seçimi yapıldığında tetiklenir."""
        if not self.is_connected_var.get() or self.is_busy:
            messagebox.showwarning("Bağlantı Yok", "Lütfen önce sunucuya bağlanın.")
            self.servo_driver_var.set("")
            return

        selection = self.servo_driver_var.get()
        driver_map = {
            "SMB": 1,
            "Yaskawa": 2,
            "inovance": 3,
            "aaaaa": 4,
            "bbbbbb": 5,
            "cccccc": 6
        }
        
        value_to_write = driver_map.get(selection)

        if value_to_write is not None:
            target_address = 0
            # Arka planda çalışması için komutu kuyruğa ekle
            self.command_queue.put((self._set_plc_byte_thread_safe, [target_address, value_to_write]))
        else:
            print(f"WARN: Geçersiz sürücü seçimi: {selection}")

    def toggle_enable(self):
        """Enable butonuna basıldığında bool 0 adresini değiştirir."""
        if not self.is_connected_var.get() or self.is_busy:
            return

        new_state = not self.enable_button_state.get()
        # Arka planda çalışması için komutu kuyruğa ekle
        self.command_queue.put((self._set_plc_bool_thread_safe, [0, new_state]))
        
        self.enable_button_state.set(new_state)
        if new_state:
            self.enable_button.config(text="DISABLE", bg="green")
        else:
            self.enable_button.config(text="ENABLE", bg="red")

    def handle_api_error(self, error, context=""):
        """Merkezi hata yönetimi ve bağlantı kesme."""
        print(f"ERROR: API call failed. {context}. Details: {error}")
        if self.is_connected_var.get():
            self.is_connected_var.set(False)
            self.update_gui_state()

    def _periodic_position_update(self):
        """Sunucudan periyodik olarak pozisyon verilerini okur."""
        if not self.is_connected_var.get() or self.is_busy:
            self.root.after(100, self._periodic_position_update)
            return

        addresses = [192, 194, 197, 193, 195, 196]
        # Arka planda çalışması için komutu kuyruğa ekle
        self.command_queue.put((self._read_positions_thread_safe, [addresses]))
        
        self.root.after(100, self._periodic_position_update)

    def _read_positions_thread_safe(self, addresses):
        """İş parçacığı içinde pozisyon okuma ve kilitleme."""
        with self.lock:
            try:
                for i, addr in enumerate(addresses):
                    dword_val = self.client.get_dword_value(addr)
                    real_val = self.dword_to_real(dword_val)
                    self.root.after(0, self.axis_value_vars[i].set, f"{real_val:.3f}")
            except (ApiError, ConnectionError) as e:
                self.handle_api_error(e, "in position update")

    def on_read_all_press(self):
        """'Read All' butonuna basıldığında tetiklenir."""
        if not self.is_connected_var.get() or self.is_busy: return
        self.is_busy = True
        print("INFO: Starting 'Read All' sequence.")
        # Arka planda çalışması için komutu kuyruğa ekle
        self.command_queue.put((self._read_all_thread_safe,))

    def _read_all_thread_safe(self):
        """
        'Read All' sekansının iş parçacığı güvenli versiyonu.
        Senkronizasyonu kilit ile sağlar.
        """
        with self.lock:
            try:
                # Adım 1: bool adresini TRUE yap
                self.client.set_plc_bool(320, True)
                time.sleep(0.05) # Küçük bir bekleme

                # Adım 2: Tüm değerleri oku
                for i in range(7):
                    address = int(self.read_dword_address_vars[i].get())
                    value = self.client.get_dword_value(address)
                    self.root.after(0, self.read_dword_value_vars[i].set, str(value))
                    print(f"INFO: Read DWORD #{i+1} from address {address} -> {value}")
                    time.sleep(0.05) # Küçük bir bekleme

                # Adım 3: bool adresini FALSE yap
                self.client.set_plc_bool(320, False)
                
                # UI güncelleme
                self.root.after(0, self.update_slider_ranges)
            except (ValueError, ApiError, ConnectionError) as e:
                self.handle_api_error(e, "in read all sequence")
                self.client.set_plc_bool(320, False)
            finally:
                self.root.after(0, lambda: setattr(self, 'is_busy', False))

    def on_single_write_press(self, index, bool_address):
        """Tek bir PID değerini yazmak için sekansı başlatır."""
        if not self.is_connected_var.get() or self.is_busy: return
        self.is_busy = True
        print(f"INFO: Starting 'Single Write' for bool_addr {bool_address}.")
        
        try:
            dword_address = int(self.write_dword_address_vars[index].get())
            dword_value = int(self.write_dword_value_vars[index].get())
            # Arka planda çalışması için komutu kuyruğa ekle
            self.command_queue.put((self._single_write_thread_safe, [dword_address, dword_value, bool_address]))
        except ValueError as e:
            messagebox.showerror("Hata", f"Geçersiz giriş: {e}")
            self.is_busy = False

    def _single_write_thread_safe(self, dword_address, dword_value, bool_address):
        """
        'Single Write' sekansının iş parçacığı güvenli versiyonu.
        Senkronizasyonu kilit ile sağlar.
        """
        with self.lock:
            try:
                # Adım 1: DWORD adresine yaz
                self.client.set_plc_dword(dword_address, dword_value)
                print(f"INFO: Wrote {dword_value} to dword_addr {dword_address}.")
                time.sleep(0.05) # Küçük bir bekleme

                # Adım 2: bool adresini TRUE yap
                self.client.set_plc_bool(bool_address, True)
                print(f"INFO: Set bool_addr {bool_address} to TRUE.")
                time.sleep(0.1) # Belirli bir süre bekle

                # Adım 3: bool adresini FALSE yap
                self.client.set_plc_bool(bool_address, False)
                print(f"INFO: Finalized 'Single Write' for bool_addr {bool_address}.")

            except (SendError, ConnectionError) as e:
                self.handle_api_error(e, "writing in single write sequence")
            finally:
                self.root.after(0, lambda: setattr(self, 'is_busy', False))

    def real_to_dword(self, real_value):
        """REAL (float) bir değeri DWORD (unsigned int) formatına dönüştürür."""
        try:
            return struct.unpack('<I', struct.pack('<f', real_value))[0]
        except Exception:
            return 0

    def send_axis_position_to_plc(self, target_address, target_var):
        """
        Seçili eksenin o anki pozisyonunu yakalar ve PLC'ye yazar.
        """
        if not self.is_connected_var.get() or self.is_busy:
            messagebox.showwarning("Bağlantı Yok", "Lütfen önce sunucuya bağlanın.")
            return

        try:
            axis_index = int(self.axis_selection_var.get())
            if not (0 <= axis_index < len(self.axis_value_vars)):
                messagebox.showwarning("Geçersiz Eksen", f"Lütfen 0 ile {len(self.axis_value_vars) - 1} arasında bir eksen numarası girin.")
                return

            current_position_str = self.axis_value_vars[axis_index].get()
            current_position_real = float(current_position_str)

            target_var.set(f"{current_position_real:.3f}")

            position_dword = self.real_to_dword(current_position_real)

            # Arka planda çalışması için komutu kuyruğa ekle
            self.command_queue.put((self._set_plc_dword_thread_safe, [target_address, position_dword]))

            print(f"INFO: Eksen {axis_index} pozisyonu ({current_position_real:.3f}) yakalandı. "
                  f"DWORD olarak ({position_dword}) adres {target_address}'e yazma komutu kuyruğa eklendi.")

        except ValueError:
            messagebox.showerror("Hatalı Giriş", "Lütfen Eksen Seçimi için geçerli bir sayı girin veya pozisyon verisinin doğru olduğundan emin olun.")
    
    def _set_plc_dword_thread_safe(self, address, value):
        """İş parçacığı içinde DWORD yazma ve kilitleme."""
        with self.lock:
            try:
                self.client.set_plc_dword(address, value)
            except (SendError, ConnectionError) as e:
                self.handle_api_error(e, f"writing dword at {address}")

    def _set_plc_bool_thread_safe(self, address, value):
        """İş parçacığı içinde BOOL yazma ve kilitleme."""
        with self.lock:
            try:
                self.client.set_plc_bool(address, value)
            except (SendError, ConnectionError) as e:
                self.handle_api_error(e, f"writing bool at {address}")

    def _set_plc_byte_thread_safe(self, address, value):
        """İş parçacığı içinde BYTE yazma ve kilitleme."""
        with self.lock:
            try:
                self.client.set_plc_byte(address, value)
            except (SendError, ConnectionError) as e:
                self.handle_api_error(e, f"writing byte at {address}")

    def _set_bool_value(self, address, value):
        """Basit bir bool değerini sunucuya gönderir (thread-safe)."""
        if not self.is_connected_var.get(): return
        self.command_queue.put((self._set_plc_bool_thread_safe, [address, value]))

    def toggle_oscillation(self):
        if not self.is_connected_var.get(): return
        self.oscillation_active = not self.oscillation_active
        if self.oscillation_active:
            self.oscillation_button.config(text="STOP Oscillation Move")
            self._set_bool_value(327, True)
        else:
            self.oscillation_button.config(text="START Oscillation Move")
            self._set_bool_value(327, False)

    def on_write_axis_button_press(self):
        if not self.is_connected_var.get() or self.is_busy: return
        try:
            axis_value = int(self.axis_selection_var.get())
            self.command_queue.put((self._set_plc_dword_thread_safe, [150, axis_value]))
        except ValueError:
            messagebox.showerror("Hata", "Lütfen eksen seçimi için geçerli bir sayı girin.")

    def toggle_jog_enable(self):
        if not self.is_connected_var.get(): return
        self.jog_enable_state = not self.jog_enable_state
        self._set_bool_value(322, self.jog_enable_state)
        color = "lightgreen" if self.jog_enable_state else "orange"
        self.jog_enable_button.config(bg=color)

    def toggle_connection(self):
        if self.is_connected_var.get():
            self.client.disconnect()
        else:
            try:
                ip, port = self.ip_var.get(), int(self.port_var.get())
                self.client.connect(ip, port)
                self.is_connected_var.set(True)
            except (ConnectionError, ValueError) as e:
                messagebox.showerror("Connection Failed", str(e))
                self.is_connected_var.set(False)
            finally:
                self.update_gui_state()

    def check_connection_status(self):
        current_status = self.client.is_connected()
        if self.is_connected_var.get() != current_status:
            self.is_connected_var.set(current_status)
            if not current_status:
                self.enable_button_state.set(False)
                self.enable_button.config(text="ENABLE", bg="red")
            self.update_gui_state()
        self.root.after(500, self.check_connection_status)

    def update_gui_state(self):
        is_connected = self.is_connected_var.get()
        self.update_led(is_connected)
        state = tk.NORMAL if is_connected else tk.DISABLED

        self.connect_button.config(text="Disconnect" if is_connected else "Connect",
                                   bg="lightblue" if is_connected else "lightgreen")

        widget_list = [self.write_axis_button, self.read_all_button, self.read_clear_all_button,
                       self.jog_enable_button, self.pos_jog_button,
                       self.neg_jog_button, self.positive_tune_button, self.negative_tune_button,
                       self.oscillation_button, self.enable_button,
                       self.servo_driver_combobox
                       ] + self.write_dword_sliders + self.single_write_buttons

        for widget in widget_list:
            widget.config(state=state)

    def dword_to_real(self, dword_value):
        try:
            return struct.unpack('<f', struct.pack('<I', dword_value))[0]
        except Exception:
            return 0.0

    def clear_read_values(self):
        for var in self.read_dword_value_vars:
            var.set("")
        print("INFO: All DWORD read values cleared.")

    def update_led(self, is_connected):
        self.led_canvas.itemconfig("led_oval", fill="green" if is_connected else "red")

    def update_write_value_from_slider(self, value, index):
        self._slider_update_active = True
        self.write_dword_value_vars[index].set(str(int(float(value))))
        self._slider_update_active = False

    def update_slider_from_entry(self, index, *args):
        if self._slider_update_active: return
        try:
            value = int(self.write_dword_value_vars[index].get())
            slider = self.write_dword_sliders[index]
            if not (slider.cget("from") <= value <= slider.cget("to")):
                from_val = int(value * 0.5) if value >= 100 else 0
                to_val = int(value * 1.5) if value >= 100 else 100
                slider.config(from_=from_val, to=to_val)
            slider.set(value)
        except (ValueError, tk.TclError):
            pass

    def update_slider_ranges(self):
        for i in range(7):
            try:
                read_value = int(self.read_dword_value_vars[i].get())
                from_val = int(read_value * 0.5) if read_value >= 100 else 0
                to_val = int(read_value * 1.5) if read_value >= 100 else 100
                self.write_dword_sliders[i].config(from_=from_val, to=to_val)
                self.write_dword_value_vars[i].set(str(read_value))
            except (ValueError, tk.TclError):
                self.write_dword_sliders[i].config(from_=0, to=1000)
                
    def on_closing(self):
        print("INFO: Exiting application. Disconnecting...")
        if self.client and self.client.is_connected():
            try:
                self._set_bool_value(0, False)
            except Exception as e:
                print(f"WARN: Could not reset enable state on exit: {e}")
            self.client.disconnect()
        self.root.destroy()
        # Uygulama kapandığında işçi iş parçacığının bitmesini bekle
        self.command_queue.join()

if __name__ == "__main__":
    root = tk.Tk()
    app = CNCClientApp(root)
    root.mainloop()
