import serial
import time

for port in ['COM3', 'COM4']:
    print(f"\n--- Trying {port} ---")
    try:
        with serial.Serial(port, baudrate=4800, bytesize=8, parity='N', stopbits=2, timeout=1) as ser:
            ser.reset_input_buffer()
            ser.write(b'SS\r\n')
            time.sleep(1)  # Wait a bit longer

            for i in range(8):
                line = ser.readline().decode(errors="ignore").strip()
                print(f"Channel {i}: '{line}'")
    except Exception as e:
        print(f"[!] Failed to open {port}: {e}")
