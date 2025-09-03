import tkinter as tk
from tkinter import messagebox
import os
import threading
import time
import sys

# Assuming the provided mil_api.py file is in the same directory.
# Import the Client class and relevant exceptions.

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mil_api import Client, ConnectionError, ApiError, SendError

class CNCClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MILTEKSAN CNC Client - 7 DWORD")
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

        # Connection Controls
        connection_frame = tk.LabelFrame(main_frame, text="Connection", padx=5, pady=5)
        connection_frame.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        tk.Label(connection_frame, text="IP Address:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        tk.Entry(connection_frame, textvariable=self.ip_var, width=15).grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        tk.Label(connection_frame, text="Port:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        tk.Entry(connection_frame, textvariable=self.port_var, width=15).grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        self.connect_button = tk.Button(connection_frame, text="Connect", command=self.toggle_connection)
        self.connect_button.grid(row=2, column=0, columnspan=2, pady=5, sticky="ew")

        # Connection Status LED
        self.led_canvas = tk.Canvas(connection_frame, width=20, height=20, bg='gray', highlightthickness=1, relief='sunken')
        self.led_canvas.create_oval(2, 2, 18, 18, fill="red", outline="black", tags="led_oval")
        self.led_canvas.grid(row=0, column=2, rowspan=2, padx=10, pady=5)
        
        # Frame for PID Parameters
        pid_frame = tk.LabelFrame(main_frame, text="PID Parametreleri", padx=5, pady=5)
        pid_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        # Create header row for PID parameters
        tk.Label(pid_frame, text="Parametre", font=("Arial", 9, "bold")).grid(row=0, column=0, padx=5, pady=2)
        tk.Label(pid_frame, text="Read Adres", font=("Arial", 9, "bold")).grid(row=0, column=1, padx=5, pady=2)
        tk.Label(pid_frame, text="Read Değer", font=("Arial", 9, "bold")).grid(row=0, column=2, padx=5, pady=2)
        tk.Label(pid_frame, text="Write Adres", font=("Arial", 9, "bold")).grid(row=0, column=3, padx=5, pady=2)
        tk.Label(pid_frame, text="Write Değer", font=("Arial", 9, "bold")).grid(row=0, column=4, padx=5, pady=2)
        
        pid_labels = ["Kp_Cur:", "Ki_Cur:", "Kd_Cur:", "Kp_Vel:", "Ki_Vel:", "Kp_Pos:", "Ki_Pos:"]
        
        for i in range(7):
            # Parametre Label
            tk.Label(pid_frame, text=pid_labels[i]).grid(row=i+1, column=0, padx=5, pady=2, sticky="w")

            # Read Adres Entry
            tk.Entry(pid_frame, textvariable=self.read_dword_address_vars[i], width=10).grid(row=i+1, column=1, padx=5, pady=2)
            
            # Read Değer Display
            tk.Label(pid_frame, textvariable=self.read_dword_value_vars[i], relief="sunken", width=10, anchor="center").grid(row=i+1, column=2, padx=5, pady=2, sticky="ew")
            
            # Write Adres Entry
            tk.Entry(pid_frame, textvariable=self.write_dword_address_vars[i], width=10).grid(row=i+1, column=3, padx=5, pady=2)

            # Write Değer Entry
            tk.Entry(pid_frame, textvariable=self.write_dword_value_vars[i], width=10).grid(row=i+1, column=4, padx=5, pady=2)

        # Read All button - now configured to act as a trigger for address 320
        self.read_all_button = tk.Button(pid_frame, text="Read All DWORDs (Trigger Address 320)",
                                       bg="lightcoral", activebackground="red", font=("Arial", 9, "bold"))
        self.read_all_button.grid(row=8, column=0, columnspan=3, pady=10, sticky="ew")
        self.read_all_button.bind("<ButtonPress-1>", self.on_read_button_press)
        self.read_all_button.bind("<ButtonRelease-1>", self.on_read_button_release)
        
        # Write All bool button with address 321
        self.write_all_button = tk.Button(pid_frame, text="Write All DWORDs",
                                         bg="lightgreen", activebackground="darkgreen")
        self.write_all_button.grid(row=8, column=3, columnspan=2, pady=10, sticky="ew")

        self.write_all_button.bind("<ButtonPress-1>", self.on_write_button_press)
        self.write_all_button.bind("<ButtonRelease-1>", self.on_write_button_release)
        
        # Clear All button
        self.read_clear_all_button = tk.Button(pid_frame, text="Clear All Values", 
                                        command=self.clear_read_values,
                                        bg="lightgray", activebackground="gray")
        self.read_clear_all_button.grid(row=9, column=0, columnspan=5, pady=2, sticky="ew")
        
        # Make the columns in the main frame resize proportionally
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        
        # Make the columns in the new pid_frame resize proportionally
        pid_frame.grid_columnconfigure(0, weight=1)
        pid_frame.grid_columnconfigure(1, weight=1)
        pid_frame.grid_columnconfigure(2, weight=1)
        pid_frame.grid_columnconfigure(3, weight=1)
        pid_frame.grid_columnconfigure(4, weight=1)
        
    def update_led(self, is_connected):
        """Updates the color of the LED based on the connection status."""
        color = "green" if is_connected else "red"
        self.led_canvas.itemconfig("led_oval", fill=color)

    def toggle_connection(self):
        """Handles the connect/disconnect button click event."""
        if self.is_connected_var.get():
            print("INFO: Disconnect button pressed.")
            self.client.disconnect()
            self.update_gui_state()
        else:
            try:
                ip_address = self.ip_var.get()
                port_number = int(self.port_var.get())
                
                if not (0 <= port_number <= 65535):
                    print("ERROR: Port number must be between 0 and 65535.")
                    return
                
                threading.Thread(target=self.attempt_connection, args=(ip_address, port_number), daemon=True).start()
                
            except ValueError:
                print("ERROR: Port number must be a valid integer.")
            except Exception as e:
                print(f"ERROR: An unexpected error occurred: {e}")

    def attempt_connection(self, ip_address, port_number):
        """Attempts to connect and updates the GUI on success or failure."""
        try:
            print(f"INFO: Attempting to connect to {ip_address}:{port_number}...")
            self.client.connect(ip_address, port_number)
            self.is_connected_var.set(True)
            self.update_gui_state()
            print("INFO: Successfully connected to CNC server.")
        except ConnectionError as e:
            self.is_connected_var.set(False)
            print(f"ERROR: Failed to connect: {e}")
        finally:
            self.update_gui_state()

    def check_connection_status(self):
        """Periodically checks the connection status and updates the GUI."""
        current_status = self.client.is_connected()
        if self.is_connected_var.get() != current_status:
            self.is_connected_var.set(current_status)
            self.update_gui_state()
        
        self.root.after(500, self.check_connection_status)

    def update_gui_state(self):
        """Updates the button text, color, and controls based on connection status."""
        is_connected = self.is_connected_var.get()
        self.update_led(is_connected)
        if is_connected:
            self.connect_button.config(text="Disconnect", bg="lightblue", activebackground="blue")
            self.read_all_button.config(state=tk.NORMAL)
            self.read_clear_all_button.config(state=tk.NORMAL)
            self.write_all_button.config(state=tk.NORMAL)
        else:
            self.connect_button.config(text="Connect", bg="lightgreen", activebackground="green")
            self.read_all_button.config(state=tk.DISABLED)
            self.read_clear_all_button.config(state=tk.DISABLED)
            self.write_all_button.config(state=tk.DISABLED)

    def on_read_button_press(self, event):
        """Sends a TRUE value to address 320, waits 100ms, then reads all DWORDs."""
        if not self.is_connected_var.get():
            print("WARNING: Please connect to the server first.")
            return

        def task():
            try:
                # Set boolean trigger at address 320 to TRUE
                self.client.set_plc_bool(320, True)
                print(f"INFO: Sent boolean value True to address 320 (Read Trigger).")
                
                # Wait for 100ms
                time.sleep(0.1)

                # Read all DWORD values
                self.read_all_dword_values()
            except SendError as e:
                print(f"ERROR: Failed to send boolean value: {e}")
            except ConnectionError as e:
                print(f"ERROR: Connection lost: {e}")
                self.is_connected_var.set(False)
                self.update_gui_state()
            except Exception as e:
                print(f"ERROR: An unexpected error occurred: {e}")

        threading.Thread(target=task, daemon=True).start()

    def on_read_button_release(self, event):
        """Sends a FALSE value to address 320 when the button is released."""
        if not self.is_connected_var.get():
            return
            
        def task():
            try:
                self.client.set_plc_bool(320, False)
                print(f"INFO: Sent boolean value False to address 320 (Read Trigger).")
            except SendError as e:
                print(f"ERROR: Failed to send boolean value: {e}")
            except ConnectionError as e:
                print(f"ERROR: Connection lost: {e}")
                self.is_connected_var.set(False)
                self.update_gui_state()
            except Exception as e:
                print(f"ERROR: An unexpected error occurred: {e}")

        threading.Thread(target=task, daemon=True).start()

    def on_write_button_press(self, event):
        """
        Starts a single thread to first write all DWORD values and then
        set the trigger boolean to TRUE.
        """
        if not self.is_connected_var.get():
            print("WARNING: Please connect to the server first.")
            return

        def task():
            # Tüm DWORD değerlerini senkron bir şekilde yazar.
            self._write_all_dword_values_sync()

            # Değerler yazıldıktan sonra boolean sinyalini TRUE olarak gönderir.
            try:
                address = int(self.write_bool_address_var.get())
                self.client.set_plc_bool(address, True)
                print(f"INFO: Sent boolean value True to address {address}.")
            except ValueError:
                print("ERROR: Boolean address must be a valid integer.")
            except SendError as e:
                print(f"ERROR: Failed to send boolean value: {e}")
            except ConnectionError as e:
                print(f"ERROR: Connection lost: {e}")
                self.root.after(0, self.is_connected_var.set, False)
                self.root.after(0, self.update_gui_state)
        
        threading.Thread(target=task, daemon=True).start()

    def on_write_button_release(self, event):
        """Sets the trigger boolean to FALSE when the button is released."""
        if not self.is_connected_var.get():
            return
            
        def task():
            try:
                address = int(self.write_bool_address_var.get())
                self.client.set_plc_bool(address, False)
                print(f"INFO: Sent boolean value False to address {address}.")
            except ValueError:
                print("ERROR: Boolean address must be a valid integer.")
            except SendError as e:
                print(f"ERROR: Failed to send boolean value: {e}")
            except ConnectionError as e:
                print(f"ERROR: Connection lost: {e}")
                self.root.after(0, self.is_connected_var.set, False)
                self.root.after(0, self.update_gui_state)
            except Exception as e:
                print(f"ERROR: An unexpected error occurred: {e}")

        threading.Thread(target=task, daemon=True).start()

    def read_all_dword_values(self):
        """
        Reads all 7 DWORD values from the PLC addresses.
        This function runs in a separate thread.
        """
        if not self.is_connected_var.get():
            print("WARNING: Please connect to the server first.")
            return

        # Validate all addresses first
        addresses = []
        for i in range(7):
            try:
                address = int(self.read_dword_address_vars[i].get())
                addresses.append(address)
            except ValueError:
                print(f"ERROR: Address for Read DWORD #{i+1} must be a valid integer.")
                return

        def task():
            success_count = 0
            for i, address in enumerate(addresses):
                try:
                    value = self.client.get_dword_value(address)
                    # Update the StringVar in the main thread
                    self.root.after(0, self.read_dword_value_vars[i].set, str(value))
                    print(f"INFO: Read DWORD #{i+1} value {value} from address {address}.")
                    success_count += 1
                    
                    # Small delay between reads to prevent overwhelming the system
                    time.sleep(0.1)
                    
                except ApiError as e:
                    self.root.after(0, self.read_dword_value_vars[i].set, "ERROR")
                    print(f"ERROR: Failed to read DWORD #{i+1} from address {address}: {e}")
                except ConnectionError as e:
                    print(f"ERROR: Connection lost while reading DWORD #{i+1}: {e}")
                    self.root.after(0, self.is_connected_var.set, False)
                    self.root.after(0, self.update_gui_state)
                    # Set remaining values to connection error
                    for j in range(i, 7):
                        self.root.after(0, self.read_dword_value_vars[j].set, "CONN. ERROR")
                    break
            
            if success_count > 0:
                print(f"INFO: Successfully read {success_count} out of 7 DWORD values.")

        threading.Thread(target=task, daemon=True).start()

    def _write_all_dword_values_sync(self):
        """
        Writes all 7 DWORD values to the PLC addresses synchronously.
        Bu fonksiyon ayrı bir thread'de çalıştırılmalıdır.
        """
        write_pairs = []
        for i in range(7):
            try:
                address = int(self.write_dword_address_vars[i].get())
                value = int(self.write_dword_value_vars[i].get())
                write_pairs.append((address, value))
            except ValueError:
                print(f"ERROR: Address or Value for Write DWORD #{i+1} must be a valid integer.")
                return False

        success_count = 0
        for i, (address, value) in enumerate(write_pairs):
            try:
                self.client.set_plc_dword(address, value)
                print(f"INFO: Wrote DWORD #{i+1} value {value} to address {address}.")
                success_count += 1
                
                # Yazma işlemleri arasında küçük bir gecikme
                time.sleep(0.1)

            except SendError as e:
                print(f"ERROR: Failed to write DWORD #{i+1} to address {address}: {e}")
                return False
            except ConnectionError as e:
                print(f"ERROR: Connection lost while writing DWORD #{i+1}: {e}")
                self.root.after(0, self.is_connected_var.set, False)
                self.root.after(0, self.update_gui_state)
                return False

        if success_count > 0:
            print(f"INFO: Successfully wrote {success_count} out of 7 DWORD values.")
        return True

    def clear_read_values(self):
        """Clears all DWORD value displays in the Read section."""
        for i in range(7):
            self.read_dword_value_vars[i].set("")
        print("INFO: All DWORD read values cleared.")
    
    def on_closing(self):
        """Called when the window is closed. Ensures the client disconnects gracefully."""
        print("INFO: Exiting application. Disconnecting...")
        self.client.disconnect()
        self.root.destroy()

# Main application entry point
if __name__ == "__main__":
    if not os.path.exists("mil_api.py"):
        print("ERROR: 'mil_api.py' file not found. Please ensure it is in the same directory.")
    else:
        root = tk.Tk()
        app = CNCClientApp(root)
        root.mainloop()
