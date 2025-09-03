import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from mil_api import Client, ConnectionError, ApiError, SendError

class CNCGui:
    def __init__(self, root):
        self.root = root
        self.root.title("CNC Kontrol")
        self.root.geometry("450x300")
        
        self.client = None
        self.connected = False
        
        # Ana frame
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        self.create_connection_section(main_frame)
        self.create_read_section(main_frame)
        self.create_write_section(main_frame)

    def create_connection_section(self, parent):
        """Bağlantı bölümü"""
        conn_frame = ttk.LabelFrame(parent, text="Bağlantı", padding="10")
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        
        # IP
        ip_frame = ttk.Frame(conn_frame)
        ip_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(ip_frame, text="IP:").pack()
        self.ip_entry = ttk.Entry(ip_frame, width=15)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.pack()
        
        # Port
        port_frame = ttk.Frame(conn_frame)
        port_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(port_frame, text="Port:").pack()
        self.port_entry = ttk.Entry(port_frame, width=10)
        self.port_entry.insert(0, "60000")
        self.port_entry.pack()
        
        # Connect butonu
        btn_frame = ttk.Frame(conn_frame)
        btn_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Label(btn_frame, text="").pack()  # Boş label hizalama için
        self.connect_btn = ttk.Button(btn_frame, text="Bağlan", command=self.toggle_connection)
        self.connect_btn.pack()
        
        # LED durum
        led_frame = ttk.Frame(conn_frame)
        led_frame.pack(side=tk.LEFT)
        ttk.Label(led_frame, text="Durum:").pack()
        self.led_label = tk.Label(led_frame, text="●", font=("Arial", 20), fg="red")
        self.led_label.pack()

    def create_read_section(self, parent):
        """1 adres okuma bölümü"""
        read_frame = ttk.LabelFrame(parent, text="Dword Okuma", padding="10")
        read_frame.pack(fill=tk.X, pady=(0, 10))
        
        control_frame = ttk.Frame(read_frame)
        control_frame.pack()
        
        ttk.Label(control_frame, text="Dword Adres:").pack(side=tk.LEFT, padx=(0, 10))
        self.read_addr = ttk.Entry(control_frame, width=10)
        self.read_addr.pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(control_frame, text="Sonuç:").pack(side=tk.LEFT, padx=(0, 10))
        self.read_result = tk.StringVar(value="-")
        ttk.Label(control_frame, textvariable=self.read_result, relief=tk.SUNKEN, width=15).pack(side=tk.LEFT)

    def create_write_section(self, parent):
        """Bool write bölümü"""
        write_frame = ttk.LabelFrame(parent, text="Bool Write", padding="10")
        write_frame.pack(fill=tk.X)
        
        control_frame = ttk.Frame(write_frame)
        control_frame.pack()
        
        ttk.Label(control_frame, text="Bool Adres:").pack(side=tk.LEFT, padx=(0, 10))
        self.write_addr = ttk.Entry(control_frame, width=10)
        self.write_addr.pack(side=tk.LEFT, padx=(0, 20))
        
        # Read butonu (aslında write yapıyor)
        self.read_btn_write = tk.Button(control_frame, text="Read", bg="lightgreen", 
                                       font=("Arial", 12), width=8)
        self.read_btn_write.pack(side=tk.LEFT)
        
        # Mouse olayları
        self.read_btn_write.bind("<ButtonPress-1>", self.write_true)
        self.read_btn_write.bind("<ButtonRelease-1>", self.write_false)

    def toggle_connection(self):
        if not self.connected:
            self.connect()
        else:
            self.disconnect()

    def connect(self):
        ip = self.ip_entry.get().strip()
        port_text = self.port_entry.get().strip()
        
        if not ip:
            messagebox.showerror("Hata", "IP boş")
            return
            
        if not port_text:
            messagebox.showerror("Hata", "Port boş")
            return
            
        try:
            port = int(port_text)
        except ValueError:
            messagebox.showerror("Hata", "Port geçersiz")
            return
        
        self.connect_btn.configure(state="disabled", text="Bağlanıyor...")
        
        def connect_thread():
            try:
                self.client = Client()
                self.client.connect(ip, port)
                self.root.after(0, self.connection_success, ip, port)
            except Exception as e:
                self.root.after(0, self.connection_failed, str(e))
        
        threading.Thread(target=connect_thread, daemon=True).start()

    def connection_success(self, ip, port):
        self.connected = True
        self.connect_btn.configure(state="normal", text="Bağlantıyı Kes")
        self.led_label.configure(fg="green")

    def connection_failed(self, error):
        self.connect_btn.configure(state="normal", text="Bağlan")
        self.led_label.configure(fg="red")
        messagebox.showerror("Bağlantı Hatası", error)

    def disconnect(self):
        try:
            if self.client:
                self.client.disconnect()
                self.client = None
        except Exception as e:
            print(f"Disconnect hatası: {e}")
        finally:
            self.connected = False
            self.connect_btn.configure(text="Bağlan")
            self.led_label.configure(fg="red")

    def update_result(self, index, result):
        """Sonucu güncelle"""
        self.results[index].configure(text=result)

    def write_true(self, event):
        """Bas - 1 yaz, sonra 300ms bekle ve tek adres oku"""
        if not self.connected:
            return
        
        bool_addr_text = self.write_addr.get().strip()
        if not bool_addr_text:
            return
            
        try:
            bool_address = int(bool_addr_text)
        except ValueError:
            return
            
        def write_and_read_thread():
            try:
                # 1. Bool adresine True yaz
                self.client.set_plc_bool(bool_address, True)
                print(f"Bool {bool_address} adresine 1 yazıldı")
                
                # 2. 300ms bekle
                time.sleep(0.3)
                print("300ms beklendi, dword okumaya başlanıyor")
                
                # 3. Tek dword adresini oku - sadece dolu ise
                dword_addr_text = self.read_addr.get().strip()
                if dword_addr_text:
                    try:
                        dword_address = int(dword_addr_text)
                        print(f"Dword okuma deneniyor: adres {dword_address}")
                        
                        # Uint32 (dword) oku
                        result = self.client.
                        print(f"Adres {dword_address} uint32 sonuç: {result}")
                        
                        # Sonucu göster
                        self.root.after(0, lambda: self.read_result.set(str(result)))
                        
                    except ValueError:
                        print(f"Geçersiz dword adres: {dword_addr_text}")
                        self.root.after(0, lambda: self.read_result.set("ADRES_HATASI"))
                    except Exception as e:
                        print(f"Dword okuma hatası: {e}")
                        self.root.after(0, lambda: self.read_result.set("OKUMA_HATASI"))
                        
            except Exception as e:
                print(f"Bool write hatası: {e}")
        
        threading.Thread(target=write_and_read_thread, daemon=True).start()

    def write_false(self, event):
        """Bırak - 0 yaz"""
        if not self.connected:
            return
        
        addr_text = self.write_addr.get().strip()
        if not addr_text:
            return
            
        try:
            address = int(addr_text)
        except ValueError:
            return
            
        def write_thread():
            try:
                self.client.set_plc_bool(address, False)
            except Exception as e:
                print(f"Write hatası: {e}")
        
        threading.Thread(target=write_thread, daemon=True).start()

    def write_true(self, event):
        """Bas - sadece 1 yaz"""
        if not self.connected:
            return
        
        bool_addr_text = self.write_addr.get().strip()
        if not bool_addr_text:
            return
            
        try:
            bool_address = int(bool_addr_text)
        except ValueError:
            return
            
        def write_thread():
            try:
                # Bool adresine True yaz
                self.client.set_plc_bool(bool_address, True)
                print(f"Bool {bool_address} adresine 1 yazıldı")
            except Exception as e:
                print(f"Bool write 1 hatası: {e}")
        
        threading.Thread(target=write_thread, daemon=True).start()

    def write_false(self, event):
        """Bırak - 0 yaz VE 300ms sonra oku"""
        if not self.connected:
            return
        
        bool_addr_text = self.write_addr.get().strip()
        if not bool_addr_text:
            return
            
        try:
            bool_address = int(bool_addr_text)
        except ValueError:
            return
            
        def write_and_read_thread():
            try:
                # 1. Bool adresine False yaz
                self.client.set_plc_bool(bool_address, False)
                print(f"Bool {bool_address} adresine 0 yazıldı")
                
                # 2. 300ms bekle
                time.sleep(0.3)
                print("300ms beklendi, dword okumaya başlanıyor")
                
                # 3. Dword adresini oku
                dword_addr_text = self.read_addr.get().strip()
                if dword_addr_text:
                    try:
                        dword_address = int(dword_addr_text)
                        print(f"Dword okuma deneniyor: adres {dword_address}")
                        
                        # Uint32 oku
                        result = self.client.get_dword_value(dword_address)
                        print(f"Adres {dword_address} uint32 sonuç: {result}")
                        
                        # Sonucu göster
                        self.root.after(0, lambda: self.read_result.set(str(result)))
                        
                    except ValueError:
                        print(f"Geçersiz dword adres: {dword_addr_text}")
                        self.root.after(0, lambda: self.read_result.set("ADRES_HATASI"))
                    except Exception as e:
                        print(f"Dword okuma hatası: {e}")
                        self.root.after(0, lambda: self.read_result.set("OKUMA_HATASI"))
                        
            except Exception as e:
                print(f"Bool write/read hatası: {e}")
        
        threading.Thread(target=write_and_read_thread, daemon=True).start()

    def __del__(self):
        """Temizlik"""
        try:
            if self.client:
                self.client.disconnect()
        except:
            pass

def main():
    root = tk.Tk()
    try:
        app = CNCGui(root)
        root.mainloop()
    except Exception as e:
        print(f"Ana hata: {e}")
    finally:
        try:
            root.destroy()
        except:
            pass

if __name__ == "__main__":
    main()