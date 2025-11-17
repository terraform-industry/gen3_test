#!/usr/bin/env python3
import serial
import time
import sys

COM_PORT = "COM8"
BAUD_RATE = 9600
GASES = {"7782-44-7": "O2", "1333-74-0": "H2", "7727-37-9": "N2"}
CAS = {v: k for k, v in GASES.items()}
OVERLOAD = 9.9E37  # BGA overload value

def cmd(ser, text, read=True):
    ser.write((text + "\r").encode())
    time.sleep(0.05)
    if not read:
        return None
    try:
        data = ser.read(ser.in_waiting or 1024).decode().strip()
        return data.split('\n')[-1] if data else None
    except:
        return None

def get_num(text):
    if not text:
        return None
    for part in text.replace('%', '').split():
        try:
            val = float(part)
            # Check for overload value
            if val >= OVERLOAD:
                return 0.0
            return val
        except:
            pass
    return None

def main():
    # Handle command line args
    if len(sys.argv) == 3:
        p, s = sys.argv[1].upper(), sys.argv[2].upper()
        if p not in CAS or s not in CAS:
            print(f"Error: Use {list(CAS.keys())}")
            sys.exit(1)
        set_gas = True
    else:
        set_gas = False
    
    # Connect
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=0.2)
    print(f"Connected to {COM_PORT} at {BAUD_RATE} baud")
    
    # Set gases if requested
    if set_gas:
        cmd(ser, f"GASP {CAS[p]}", False)
        cmd(ser, f"GASS {CAS[s]}", False)
        print(f"Set: {p} in {s}")
    
    # Poll loop
    print("Reading...")
    while True:
        pg = GASES.get(cmd(ser, "GASP?"), cmd(ser, "GASP?"))
        sg = GASES.get(cmd(ser, "GASS?"), cmd(ser, "GASS?"))
        pur = get_num(cmd(ser, "RATO? 1%"))
        unc = get_num(cmd(ser, "UNCT?%"))
        tc = get_num(cmd(ser, "TCEL? C"))
        ps = get_num(cmd(ser, "PRES?"))
        
        # Display NA for disconnected state
        pg_str = pg if pg else "NA"
        sg_str = sg if sg else "NA"
        
        print(f"Primary={pg_str}  Secondary={sg_str}  "
              f"Purity={f'{pur:.3f}' if pur is not None else 'NA'}%  "
              f"Unc=±{f'{unc:.3f}' if unc is not None else 'NA'}%  "
              f"T={f'{tc:.3f}' if tc is not None else 'NA'}C  "
              f"P={f'{ps:.3f}' if ps is not None else 'NA'}psi")
        
        time.sleep(0.5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")