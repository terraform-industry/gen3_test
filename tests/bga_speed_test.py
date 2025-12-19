#!/usr/bin/env python3
"""
BGA244 Serial Speed Test
Measures maximum achievable sample rate for BGA readings
"""

import serial
import time
import statistics

# Configuration - match your working setup
COM_PORT = "COM3"  # Change to COM8 or COM10 as needed
BAUD_RATE = 9600

def cmd(ser, text, read=True):
    """Send command and optionally read response"""
    ser.write((text + "\r").encode())
    time.sleep(0.02)  # Reduced from 0.05 for speed test
    if not read:
        return None
    try:
        data = ser.read(ser.in_waiting or 1024).decode().strip()
        return data.split('\n')[-1] if data else None
    except:
        return None

def get_num(text):
    """Extract number from response"""
    if not text:
        return None
    for part in text.replace('%', '').split():
        try:
            return float(part)
        except:
            pass
    return None

print(f"BGA Speed Test")
print(f"Port: {COM_PORT}, Baud: {BAUD_RATE}")
print("=" * 50)

# Connect
ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=0.2)
print(f"Connected to {COM_PORT}")

# Verify connection
pg = cmd(ser, "GASP?")
print(f"Primary gas: {pg}")

# Test 1: Single command timing
print("\n" + "=" * 50)
print("Test 1: Single command timing (RATO? 1%)...")
read_times = []

for i in range(100):
    start = time.perf_counter()
    result = cmd(ser, "RATO? 1%")
    elapsed = time.perf_counter() - start
    if result is not None:
        read_times.append(elapsed)

if read_times:
    avg_time = statistics.mean(read_times)
    min_time = min(read_times)
    max_time = max(read_times)
    std_dev = statistics.stdev(read_times) if len(read_times) > 1 else 0
    
    print(f"\n  Samples: {len(read_times)}/100 successful")
    print(f"  Min time:  {min_time*1000:.1f} ms")
    print(f"  Max time:  {max_time*1000:.1f} ms")
    print(f"  Avg time:  {avg_time*1000:.1f} ms")
    print(f"  Std dev:   {std_dev*1000:.1f} ms")
    print(f"\n  Single command max rate: {1/avg_time:.1f} Hz")

# Test 2: Full poll cycle (all 6 commands like in ws_rs422_bga.py)
print("\n" + "=" * 50)
print("Test 2: Full poll cycle (6 commands: GASP?, GASS?, RATO?, UNCT?, TCEL?, PRES?)...")
cycle_times = []

for i in range(50):
    start = time.perf_counter()
    pg = cmd(ser, "GASP?")
    sg = cmd(ser, "GASS?")
    pur = get_num(cmd(ser, "RATO? 1%"))
    unc = get_num(cmd(ser, "UNCT?%"))
    tc = get_num(cmd(ser, "TCEL? C"))
    ps = get_num(cmd(ser, "PRES?"))
    elapsed = time.perf_counter() - start
    
    if pur is not None:  # At least purity should work
        cycle_times.append(elapsed)

if cycle_times:
    avg_time = statistics.mean(cycle_times)
    min_time = min(cycle_times)
    max_time = max(cycle_times)
    
    print(f"\n  Samples: {len(cycle_times)}/50 successful")
    print(f"  Min cycle time:  {min_time*1000:.1f} ms")
    print(f"  Max cycle time:  {max_time*1000:.1f} ms")
    print(f"  Avg cycle time:  {avg_time*1000:.1f} ms")
    print(f"\n  Full poll max rate: {1/avg_time:.1f} Hz")

# Test 3: Purity-only polling (just RATO? for fastest updates)
print("\n" + "=" * 50)
print("Test 3: Purity-only sustained throughput (10 seconds)...")

successful = 0
failed = 0
start_time = time.perf_counter()
duration = 10.0

while (time.perf_counter() - start_time) < duration:
    result = get_num(cmd(ser, "RATO? 1%"))
    if result is not None:
        successful += 1
    else:
        failed += 1

elapsed = time.perf_counter() - start_time
actual_rate = successful / elapsed

print(f"\n  Duration: {elapsed:.1f} s")
print(f"  Successful reads: {successful}")
print(f"  Failed reads: {failed}")
print(f"  Purity-only rate: {actual_rate:.1f} Hz")

# Test 4: Minimum viable poll (purity + temp only)
print("\n" + "=" * 50)
print("Test 4: Minimal poll (RATO? + TCEL? only)...")
min_cycle_times = []

for i in range(50):
    start = time.perf_counter()
    pur = get_num(cmd(ser, "RATO? 1%"))
    tc = get_num(cmd(ser, "TCEL? C"))
    elapsed = time.perf_counter() - start
    
    if pur is not None:
        min_cycle_times.append(elapsed)

if min_cycle_times:
    avg_time = statistics.mean(min_cycle_times)
    print(f"\n  Avg cycle time: {avg_time*1000:.1f} ms")
    print(f"  2-command poll rate: {1/avg_time:.1f} Hz")

# Test 5: Command delay sensitivity
print("\n" + "=" * 50)
print("Test 5: Command delay sensitivity...")

delays = [0.01, 0.02, 0.03, 0.05, 0.1]

for delay in delays:
    times = []
    for _ in range(20):
        start = time.perf_counter()
        ser.write(("RATO? 1%" + "\r").encode())
        time.sleep(delay)
        try:
            data = ser.read(ser.in_waiting or 1024).decode().strip()
            if data:
                times.append(time.perf_counter() - start)
        except:
            pass
    
    if times:
        avg = statistics.mean(times)
        success = len(times)
        print(f"  Delay {delay*1000:4.0f}ms: {success}/20 success, avg {avg*1000:.1f} ms, ~{1/avg:.1f} Hz")

ser.close()
print("\n" + "=" * 50)
print("Done!")

