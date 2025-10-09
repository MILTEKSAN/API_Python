import tkinter as tk
from tkinter import messagebox
import os
import threading
import time
import sys
import struct

# Assuming the provided mil_api.py file is in the same directory.
# Import the Client class and relevant exceptions.

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mil_api import Client, ConnectionError, ApiError, SendError

class CNCClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MILTEKSAN TUNE API")
        # Allow window to be resizable

        try:
            self.client = Client()
        except ApiError as e:
            print(f"ERROR: Failed to initialize the API client: {e}")
            self.root.destroy()
            return
        
        # UI variables
        self.ip_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="60000")
        self.write_bool_address_var = tk.StringVar(value="321")
        self.is_connected_var = tk.BooleanVar(value=False)
        
        # 7 DWORD variables for addresses and values (Read)
        self.read_dword_address_vars = []
        self.read_dword_value_vars = []

        # 7 DWORD variables for addresses and values (Write)
        self.write_dword_address_vars = []
        self.write_dword_value_vars = []
        
        # List to hold the slider widgets
        self.write_dword_sliders = []
        
        # Jog Enable State Variable
        self.jog_enable_state = False
        
        # Eksen seçimi için değişken
        self.axis_selection_var = tk.StringVar(value="0")
        
        # Yeni okuma değerleri için değişkenler
        self.positive_tune_value_var = tk.StringVar(value="")
        self.negative_tune_value_var = tk.StringVar(value="")
        
        # YENİ: Slider'dan gelen güncellemeyi izlemek için flag
        self._slider_update_active = False
        
        # YENİ: Position etiketleri için değişkenler
        self.axis_value_vars = [tk.StringVar(value="0.000") for _ in range(6)]
        
        # YENİ: Pozisyon okuma thread'i için kontrol mekanizması
        self.position_reader_thread = None
        self._stop_position_reader_event = threading.Event()
        
        # Initialize 7 DWORD address/value pairs with default addresses (Read)
        default_read_addresses = ["300", "301", "302", "303", "304", "305", "306"]
        for i in range(7):
            self.read_dword_address_vars.append(tk.StringVar(value=default_read_addresses[i]))
            self.read_dword_value_vars.append(tk.StringVar(value=""))

        # Initialize 7 DWORD address/value pairs with default addresses (Write)
        default_write_addresses = ["340", "341", "342", "343", "344", "345", "346"]
        for i in range(7):
            self.write_dword_address_vars.append(tk.StringVar(value=default_write_addresses[i]))
            self.write_dword_value_vars.append(tk.StringVar(value="0"))

        self.create_widgets()
        
        self.root.after(500, self.check_connection_status)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        # Create a frame for the main controls
        main_frame = tk.Frame(self.root, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.grid_columnconfigure(0, weight=1)

        # YENİ: Connection ve Position alanlarını tutacak üst çerçeve
        top_frame = tk.Frame(main_frame)
        top_frame.grid(row=0, column=0, sticky="ew")
        top_frame.grid_columnconfigure(0, weight=0) # Connection alanı genişlemeyecek
        top_frame.grid_columnconfigure(1, weight=1) # Position alanı genişleyecek

        # Connection Controls (Artık top_frame içinde ve daha kompakt)
        connection_frame = tk.LabelFrame(top_frame, text="Connection", padx=5, pady=5)
        connection_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ns")

        tk.Label(connection_frame, text="Eksen Seçimi (0-7):").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        tk.Entry(connection_frame, textvariable=self.axis_selection_var, width=10).grid(row=0, column=1, padx=5, pady=2, sticky="w")
        
        self.write_axis_button = tk.Button(connection_frame, text="Write Axis", 
                                          bg="lightyellow", activebackground="yellow")
        self.write_axis_button.grid(row=0, column=2, padx=5, pady=2, sticky="ew")
        self.write_axis_button.bind("<ButtonPress-1>", self.on_write_axis_button_press)

        tk.Label(connection_frame, text="IP Address:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        tk.Entry(connection_frame, textvariable=self.ip_var, width=15).grid(row=1, column=1, padx=5, pady=2, sticky="w")
        
        tk.Label(connection_frame, text="Port:").grid(row=2, column=0, padx=5, pady=2, sticky="w")
        tk.Entry(connection_frame, textvariable=self.port_var, width=15).grid(row=2, column=1, padx=5, pady=2, sticky="w")
        
        self.connect_button = tk.Button(connection_frame, text="Connect", command=self.toggle_connection)
        self.connect_button.grid(row=3, column=0, columnspan=2, pady=5, sticky="ew")

        self.led_canvas = tk.Canvas(connection_frame, width=20, height=20, bg='gray', highlightthickness=1, relief='sunken')
        self.led_canvas.create_oval(2, 2, 18, 18, fill="red", outline="black", tags="led_oval")
        self.led_canvas.grid(row=1, column=2, rowspan=2, padx=10, pady=5, sticky="ns")

        # YENİ: Position Frame
        position_frame = tk.LabelFrame(top_frame, text="Position", padx=5, pady=5)
        position_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        axis_labels = [f"axis{i}" for i in range(6)]
        for i, label_text in enumerate(axis_labels):
            tk.Label(position_frame, text=f"{label_text}:", font=("Arial", 9, "bold")).grid(row=i, column=0, padx=5, pady=2, sticky="w")
            tk.Label(position_frame, textvariable=self.axis_value_vars[i], relief="sunken", width=12, anchor="e").grid(row=i, column=1, padx=5, pady=2, sticky="ew")
        
        position_frame.grid_columnconfigure(1, weight=1)

        # Frame for PID Parameters (Artık main_frame içinde, 1. satırda)
        pid_frame = tk.LabelFrame(main_frame, text="PID Parameters", padx=5, pady=5)
        pid_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")

        # Create header row for PID parameters
        tk.Label(pid_frame, text="Parameters", font=("Arial", 9, "bold")).grid(row=0, column=0, padx=5, pady=2)
        tk.Label(pid_frame, text="Read Addres", font=("Arial", 9, "bold")).grid(row=0, column=1, padx=5, pady=2)
        tk.Label(pid_frame, text="Read Value", font=("Arial", 9, "bold")).grid(row=0, column=2, padx=5, pady=2)
        tk.Label(pid_frame, text="Write Addres", font=("Arial", 9, "bold")).grid(row=0, column=3, padx=5, pady=2)
        tk.Label(pid_frame, text="Write Value", font=("Arial", 9, "bold")).grid(row=0, column=4, padx=5, pady=2)
        tk.Label(pid_frame, text="Slider", font=("Arial", 9, "bold")).grid(row=0, column=5, padx=5, pady=2)

        pid_labels = ["Kp_Cur:", "Ki_Cur:", "Kd_Cur:", "Kp_Vel:", "Ki_Vel:", "Kp_Pos:", "Ki_Pos:"]
        
        for i in range(7):
            tk.Label(pid_frame, text=pid_labels[i]).grid(row=i+1, column=0, padx=5, pady=2, sticky="w")
            tk.Entry(pid_frame, textvariable=self.read_dword_address_vars[i], width=10).grid(row=i+1, column=1, padx=5, pady=2)
            tk.Label(pid_frame, textvariable=self.read_dword_value_vars[i], relief="sunken", width=10, anchor="center").grid(row=i+1, column=2, padx=5, pady=2, sticky="ew")
            tk.Entry(pid_frame, textvariable=self.write_dword_address_vars[i], width=10).grid(row=i+1, column=3, padx=5, pady=2)
            entry = tk.Entry(pid_frame, textvariable=self.write_dword_value_vars[i], width=10)
            entry.grid(row=i+1, column=4, padx=5, pady=2)
            slider = tk.Scale(pid_frame, from_=0, to=1000, orient=tk.HORIZONTAL, showvalue=0, command=lambda val, index=i: self.update_write_value_from_slider(val, index))
            slider.grid(row=i+1, column=5, padx=5, pady=2, sticky="ew")
            self.write_dword_sliders.append(slider)
            self.write_dword_value_vars[i].trace_add("write", lambda *args, index=i: self.update_slider_from_entry(index))
            try:
                slider.set(int(self.write_dword_value_vars[i].get()))
            except ValueError:
                slider.set(0)

        self.read_all_button = tk.Button(pid_frame, text="Read All DWORDS", bg="lightcoral", activebackground="red", font=("Arial", 9, "bold"))
        self.read_all_button.grid(row=8, column=0, columnspan=3, pady=10, sticky="ew")
        self.read_all_button.bind("<ButtonPress-1>", self.on_read_button_press)
        self.read_all_button.bind("<ButtonRelease-1>", self.on_read_button_release)
        
        self.write_all_button = tk.Button(pid_frame, text="Write All DWORDS", bg="lightgreen", activebackground="darkgreen")
        self.write_all_button.grid(row=8, column=3, columnspan=3, pady=10, sticky="ew")
        self.write_all_button.bind("<ButtonPress-1>", self.on_write_button_press)
        
        self.read_clear_all_button = tk.Button(pid_frame, text="Clear All Values", command=self.clear_read_values, bg="lightgray", activebackground="gray")
        self.read_clear_all_button.grid(row=9, column=0, columnspan=6, pady=2, sticky="ew")
        
        # --- Frame to hold JOG and Tune controls side-by-side --- (Artık main_frame içinde, 2. satırda)
        controls_parent_frame = tk.Frame(main_frame)
        controls_parent_frame.grid(row=2, column=0, sticky="ew")
        controls_parent_frame.grid_columnconfigure(0, weight=1) # Column for JOG
        controls_parent_frame.grid_columnconfigure(1, weight=1) # Column for Tune

        # --- JOG Kontrolleri ---
        jog_frame = tk.LabelFrame(controls_parent_frame, text="JOG", padx=5, pady=5)
        jog_frame.grid(row=0, column=0, padx=(5, 2), pady=5, sticky="nsew")

        self.jog_enable_button = tk.Button(jog_frame, text="JOG Enable", bg="orange", activebackground="darkorange", command=self.toggle_jog_enable)
        self.jog_enable_button.grid(row=0, column=0, columnspan=2, pady=5, sticky="ew")

        self.pos_jog_button = tk.Button(jog_frame, text="Positive JOG", bg="lightblue", activebackground="blue")
        self.pos_jog_button.grid(row=1, column=0, pady=5, padx=5, sticky="ew")
        self.pos_jog_button.bind("<ButtonPress-1>", lambda event, addr=323, val=True: self.on_jog_button_press(event, addr, val))
        self.pos_jog_button.bind("<ButtonRelease-1>", lambda event, addr=323, val=False: self.on_jog_button_release(event, addr, val))
        
        self.neg_jog_button = tk.Button(jog_frame, text="Negative JOG", bg="lightblue", activebackground="blue")
        self.neg_jog_button.grid(row=1, column=1, pady=5, padx=5, sticky="ew")
        self.neg_jog_button.bind("<ButtonPress-1>", lambda event, addr=324, val=True: self.on_jog_button_press(event, addr, val))
        self.neg_jog_button.bind("<ButtonRelease-1>", lambda event, addr=324, val=False: self.on_jog_button_release(event, addr, val))
        
        jog_frame.grid_columnconfigure(0, weight=1)
        jog_frame.grid_columnconfigure(1, weight=1)
        
        # --- Tune Position Kontrolleri ---
        tune_frame = tk.LabelFrame(controls_parent_frame, text="Selection Tune Positions", padx=5, pady=5)
        tune_frame.grid(row=0, column=1, padx=(2, 5), pady=5, sticky="nsew")
        
        self.positive_tune_button = tk.Button(tune_frame, text="Tune Position Selection", bg="lightgreen", activebackground="green")
        self.positive_tune_button.grid(row=0, column=0, pady=5, padx=5, sticky="ew")
        self.positive_tune_button.bind("<ButtonPress-1>", lambda event: self.on_tune_button_press(325, True))
        self.positive_tune_button.bind("<ButtonRelease-1>", lambda event: self.on_tune_button_release(325, False))
        
        tk.Label(tune_frame, textvariable=self.positive_tune_value_var, relief="sunken", width=12).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.negative_tune_button = tk.Button(tune_frame, text="Negative Tune Position", bg="lightcoral", activebackground="red")
        self.negative_tune_button.grid(row=1, column=0, pady=5, padx=5, sticky="ew")
        self.negative_tune_button.bind("<ButtonPress-1>", lambda event: self.on_tune_button_press(326, True))
        self.negative_tune_button.bind("<ButtonRelease-1>", lambda event: self.on_tune_button_release(326, False))
        
        tk.Label(tune_frame, textvariable=self.negative_tune_value_var, relief="sunken", width=12).grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        self.oscillation_button = tk.Button(tune_frame, text="START Oscillation Move", bg="lightyellow", activebackground="yellow")
        self.oscillation_button.grid(row=2, column=0, columnspan=2, pady=(10, 5), padx=5, sticky="ew")
        self.oscillation_button.bind("<ButtonPress-1>", lambda event: self.on_oscillation_button_press(327, True))
        self.oscillation_button.bind("<ButtonRelease-1>", lambda event: self.on_oscillation_button_release(327, False))
        
        tune_frame.grid_columnconfigure(0, weight=1)
        tune_frame.grid_columnconfigure(1, weight=1)
        
        pid_frame.grid_columnconfigure(0, weight=1)
        pid_frame.grid_columnconfigure(1, weight=1)
        pid_frame.grid_columnconfigure(2, weight=1)
        pid_frame.grid_columnconfigure(3, weight=1)
        pid_frame.grid_columnconfigure(4, weight=1)
        pid_frame.grid_columnconfigure(5, weight=2)
    
    # Pozisyonları sürekli okuyan thread'i başlatan fonksiyon
    def start_position_reading(self):
        if self.position_reader_thread is None or not self.position_reader_thread.is_alive():
            self._stop_position_reader_event.clear()
            self.position_reader_thread = threading.Thread(target=self._position_reader_loop, daemon=True)
            self.position_reader_thread.start()
            print("INFO: Position reader thread started.")

    # Pozisyonları sürekli okuyan thread'i durduran fonksiyon
    def stop_position_reading(self):
        self._stop_position_reader_event.set()
        print("INFO: Position reader thread stop signal sent.")

    # Pozisyonları okuyan thread'in ana döngüsü
    def _position_reader_loop(self):
        addresses = [192, 194, 197, 193, 195, 196]
        target_interval = 0.01  # 10 ms hedef döngü süresi
        
        print("INFO: Position reader loop entered.")

        while not self._stop_position_reader_event.is_set():
            start_time = time.monotonic()

            if self.client.is_connected():
                try:
                    for i, addr in enumerate(addresses):
                        dword_val = self.client.get_dword_value(addr)
                        real_val = self.dword_to_real(dword_val)
                        formatted_val = f"{real_val:.3f}"
                        
                        if self.root.winfo_exists():
                            self.root.after(0, self.axis_value_vars[i].set, formatted_val)
                    
                    end_time = time.monotonic()
                    elapsed_time = end_time - start_time
                    
                    sleep_time = target_interval - elapsed_time
                    if sleep_time > 0:
                        time.sleep(sleep_time)

                except (ApiError, ConnectionError) as e:
                    print(f"ERROR reading positions: {e}")
                    time.sleep(1)
            else:
                print("INFO: Position reader waiting for connection...")
                time.sleep(1)
        print("INFO: Position reader loop exited.")
        
    def dword_to_real(self, dword_value):
        """
        DWORD değerini REAL (single precision float) formatına dönüştürür.
        """
        try:
            bytes_data = struct.pack('<I', dword_value)
            real_value = struct.unpack('<f', bytes_data)[0]
            return real_value
        except Exception as e:
            print(f"ERROR: DWORD to REAL conversion failed: {e}")
            return 0.0

    def update_write_value_from_slider(self, value, index):
        self._slider_update_active = True
        int_value = int(float(value))
        self.write_dword_value_vars[index].set(str(int_value))
        self._slider_update_active = False

    def update_slider_from_entry(self, index, *args):
        if self._slider_update_active:
            return

        try:
            value_str = self.write_dword_value_vars[index].get()
            if not value_str: return
            value = int(value_str)
            slider = self.write_dword_sliders[index]
            current_from, current_to = int(slider.cget("from")), int(slider.cget("to"))
            
            if not (current_from <= value <= current_to):
                from_val = int(value * 0.5) if value >= 100 else 0
                to_val = int(value * 1.5) if value >= 100 else 100
                if from_val >= to_val: to_val = from_val + 100
                slider.config(from_=from_val, to=to_val)
            slider.set(value)
        except (ValueError, Exception) as e:
            print(f"ERROR in update_slider_from_entry: {e}")

    def update_slider_ranges(self):
        print("INFO: Updating slider ranges.")
        for i in range(7):
            try:
                read_value_str = self.read_dword_value_vars[i].get()
                if read_value_str and read_value_str not in ["ERROR", "CONN. ERROR"]:
                    read_value = int(read_value_str)
                    from_val = int(read_value * 0.5) if read_value >= 100 else 0
                    to_val = int(read_value * 1.5) if read_value >= 100 else 100
                    if from_val >= to_val: to_val = from_val + 100
                    self.write_dword_sliders[i].config(from_=from_val, to=to_val)
                    self.write_dword_value_vars[i].set(str(read_value))
                else:
                    self.write_dword_sliders[i].config(from_=0, to=1000)
            except Exception as e:
                self.write_dword_sliders[i].config(from_=0, to=1000)
                print(f"WARNING: Could not update slider #{i+1} range. Error: {e}")

    def update_led(self, is_connected):
        color = "green" if is_connected else "red"
        self.led_canvas.itemconfig("led_oval", fill=color)

    def toggle_connection(self):
        if self.is_connected_var.get():
            print("INFO: Disconnect button pressed.")
            self.stop_position_reading()
            self.client.disconnect()
            self.update_gui_state()
        else:
            try:
                ip, port = self.ip_var.get(), int(self.port_var.get())
                if not (0 <= port <= 65535):
                    messagebox.showerror("Invalid Port", "Port number must be between 0 and 65535.")
                    return
                threading.Thread(target=self.attempt_connection, args=(ip, port), daemon=True).start()
            except ValueError:
                messagebox.showerror("Invalid Input", "Port number must be a valid integer.")
            except Exception as e:
                messagebox.showerror("Error", f"An unexpected error occurred: {e}")

    def attempt_connection(self, ip_address, port_number):
        try:
            print(f"INFO: Attempting to connect to {ip_address}:{port_number}...")
            self.client.connect(ip_address, port_number)
            self.is_connected_var.set(True)
            self.start_position_reading()
            print("INFO: Successfully connected to CNC server.")
        except ConnectionError as e:
            self.is_connected_var.set(False)
            print(f"ERROR: Failed to connect: {e}")
        finally:
            self.root.after(0, self.update_gui_state)

    def check_connection_status(self):
        current_status = self.client.is_connected()
        if self.is_connected_var.get() != current_status:
            self.is_connected_var.set(current_status)
            if not current_status:
                self.stop_position_reading()
            self.update_gui_state()
        self.root.after(500, self.check_connection_status)

    def update_gui_state(self):
        is_connected = self.is_connected_var.get()
        self.update_led(is_connected)
        state = tk.NORMAL if is_connected else tk.DISABLED
        
        self.connect_button.config(text="Disconnect" if is_connected else "Connect", 
                                   bg="lightblue" if is_connected else "lightgreen",
                                   activebackground="blue" if is_connected else "green")

        for widget in [self.write_axis_button, self.read_all_button, self.read_clear_all_button, 
                       self.write_all_button, self.jog_enable_button, self.pos_jog_button, 
                       self.neg_jog_button, self.positive_tune_button, self.negative_tune_button, 
                       self.oscillation_button] + self.write_dword_sliders:
            widget.config(state=state)

    # GÜNCELLENDİ: Thread çakışmasını önlemek için senkronize okuma fonksiyonu
    def _read_all_dword_values_sync(self):
        """Reads all 7 DWORD values from the PLC addresses synchronously."""
        if not self.is_connected_var.get(): return False
        
        success_count = 0
        for i in range(7):
            try:
                address = int(self.read_dword_address_vars[i].get())
                value = self.client.get_dword_value(address)
                if self.root.winfo_exists():
                    self.root.after(0, self.read_dword_value_vars[i].set, str(value))
                print(f"INFO: Read DWORD #{i+1} value {value} from address {address}.")
                success_count += 1
                time.sleep(0.05)
            except ValueError:
                print(f"ERROR: Invalid address for Read DWORD #{i+1}.")
            except (ApiError, ConnectionError) as e:
                print(f"ERROR reading DWORD #{i+1}: {e}")
                if self.root.winfo_exists():
                    self.root.after(0, self.is_connected_var.set, False)
                    self.root.after(0, self.update_gui_state)
                for j in range(i, 7): 
                    if self.root.winfo_exists():
                        self.root.after(0, self.read_dword_value_vars[j].set, "CONN. ERROR")
                return False
        
        if success_count > 0:
            print(f"INFO: Successfully read {success_count} of 7 DWORDs.")
            if self.root.winfo_exists():
                self.root.after(0, self.update_slider_ranges)
        return True

    # GÜNCELLENDİ: Artık pozisyon okuyucuyu durdurup yeniden başlatıyor
    def on_read_button_press(self, event):
        if not self.is_connected_var.get(): return

        def task():
            self.stop_position_reading()
            if self.position_reader_thread and self.position_reader_thread.is_alive():
                self.position_reader_thread.join()
            print("INFO: Position reader stopped for manual read.")
            
            try:
                self.client.set_plc_bool(320, True)
                time.sleep(0.1)
                self._read_all_dword_values_sync()
            except (SendError, ConnectionError) as e:
                print(f"ERROR on read press: {e}")
                if self.root.winfo_exists():
                    self.is_connected_var.set(False)
                    self.update_gui_state()
            except Exception as e:
                print(f"ERROR: An unexpected error occurred: {e}")
            finally:
                print("INFO: Manual read finished, restarting position reader.")
                self.start_position_reading()
                
        threading.Thread(target=task, daemon=True).start()

    def on_read_button_release(self, event):
        if not self.is_connected_var.get(): return
        def task():
            try:
                self.client.set_plc_bool(320, False)
            except (SendError, ConnectionError) as e:
                print(f"ERROR on read release: {e}")
                if self.root.winfo_exists():
                    self.is_connected_var.set(False)
                    self.update_gui_state()
        threading.Thread(target=task, daemon=True).start()

    # GÜNCELLENDİ: Artık pozisyon okuyucuyu durdurup yeniden başlatıyor
    def on_write_button_press(self, event):
        if not self.is_connected_var.get(): return

        def task():
            self.stop_position_reading()
            if self.position_reader_thread and self.position_reader_thread.is_alive():
                self.position_reader_thread.join()
            print("INFO: Position reader stopped for manual write.")
            
            try:
                if not self._write_all_dword_values_sync():
                    return
                address = int(self.write_bool_address_var.get())
                self.client.set_plc_bool(address, True)
                time.sleep(0.1)
                self.client.set_plc_bool(address, False)
            except ValueError:
                print("ERROR: Boolean address must be a valid integer.")
            except (SendError, ConnectionError) as e:
                print(f"ERROR during write trigger: {e}")
                if self.root.winfo_exists():
                    self.root.after(0, self.is_connected_var.set, False)
                    self.root.after(0, self.update_gui_state)
            finally:
                print("INFO: Manual write finished, restarting position reader.")
                self.start_position_reading()
                
        threading.Thread(target=task, daemon=True).start()

    def on_oscillation_button_press(self, address, value):
        if not self.is_connected_var.get(): return
        def task():
            try:
                self.client.set_plc_bool(address, value)
            except (SendError, ConnectionError) as e:
                print(f"ERROR: Failed to send boolean value: {e}")
                if self.root.winfo_exists():
                    self.root.after(0, self.is_connected_var.set, False)
                    self.root.after(0, self.update_gui_state)
        threading.Thread(target=task, daemon=True).start()

    def on_oscillation_button_release(self, address, value):
        self.on_oscillation_button_press(address, value)

    def _write_all_dword_values_sync(self):
        for i in range(7):
            try:
                address = int(self.write_dword_address_vars[i].get())
                value = int(self.write_dword_value_vars[i].get())
                self.client.set_plc_dword(address, value)
                time.sleep(0.05)
            except ValueError:
                print(f"ERROR: Invalid address or value for Write DWORD #{i+1}.")
                return False
            except (SendError, ConnectionError) as e:
                print(f"ERROR writing DWORD #{i+1}: {e}")
                if self.root.winfo_exists():
                    self.root.after(0, self.is_connected_var.set, False)
                    self.root.after(0, self.update_gui_state)
                return False
        print("INFO: Successfully wrote all 7 DWORD values.")
        return True

    def clear_read_values(self):
        for var in self.read_dword_value_vars:
            var.set("")
        print("INFO: All DWORD read values cleared.")

    def on_write_axis_button_press(self, event):
        if not self.is_connected_var.get(): return
        def task():
            try:
                axis_value = int(self.axis_selection_var.get())
                self.client.set_plc_dword(150, axis_value)
            except ValueError:
                print("ERROR: Axis selection must be an integer.")
            except (SendError, ConnectionError) as e:
                print(f"ERROR writing axis selection: {e}")
                if self.root.winfo_exists():
                    self.root.after(0, self.is_connected_var.set, False)
                    self.root.after(0, self.update_gui_state)
        threading.Thread(target=task, daemon=True).start()

    def toggle_jog_enable(self):
        if not self.is_connected_var.get(): return
        def task():
            self.jog_enable_state = not self.jog_enable_state
            try:
                self.client.set_plc_bool(322, self.jog_enable_state)
                color = "lightgreen" if self.jog_enable_state else "orange"
                if self.root.winfo_exists():
                    self.root.after(0, self.jog_enable_button.config, {'bg': color})
            except (SendError, ConnectionError) as e:
                print(f"ERROR toggling JOG Enable: {e}")
                if self.root.winfo_exists():
                    self.root.after(0, self.is_connected_var.set, False)
                    self.root.after(0, self.update_gui_state)
        threading.Thread(target=task, daemon=True).start()

    def on_jog_button_press(self, event, address, value):
        self.on_oscillation_button_press(address, value)

    def on_jog_button_release(self, event, address, value):
        self.on_oscillation_button_press(address, value)

    # GÜNCELLENDİ: Artık pozisyon okuyucuyu durdurup yeniden başlatıyor
    def on_tune_button_press(self, address, value):
        if not self.is_connected_var.get(): return

        def task():
            self.stop_position_reading()
            if self.position_reader_thread and self.position_reader_thread.is_alive():
                self.position_reader_thread.join()
            print("INFO: Position reader stopped for tune operation.")

            try:
                self.client.set_plc_bool(address, value)
                time.sleep(0.1)
                
                read_address = 280 if address == 325 else 281
                dword_value = self.client.get_dword_value(read_address)
                real_value = self.dword_to_real(dword_value)
                formatted_value = f"{real_value:.3f}"
                
                var_to_set = self.positive_tune_value_var if address == 325 else self.negative_tune_value_var
                if self.root.winfo_exists():
                    self.root.after(0, var_to_set.set, formatted_value)
                print(f"INFO: Read REAL value {formatted_value} from address {read_address}.")
                    
            except (SendError, ApiError, ConnectionError) as e:
                print(f"ERROR during tune operation: {e}")
                if self.root.winfo_exists():
                    self.root.after(0, self.is_connected_var.set, False)
                    self.root.after(0, self.update_gui_state)
            finally:
                print("INFO: Tune operation finished, restarting position reader.")
                self.start_position_reading()

        threading.Thread(target=task, daemon=True).start()

    def on_tune_button_release(self, address, value):
        self.on_oscillation_button_press(address, value)

    def on_closing(self):
        print("INFO: Exiting application. Disconnecting...")
        self.stop_position_reading()
        if self.client and self.client.is_connected():
            # Thread'in tamamen durmasını bekle
            if self.position_reader_thread and self.position_reader_thread.is_alive():
                self.position_reader_thread.join(timeout=1.0)
            self.client.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = CNCClientApp(root)
    root.mainloop()

