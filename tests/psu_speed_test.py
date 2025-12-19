#!/usr/bin/env python3
"""
PSU Modbus Speed Test
Measures maximum achievable sample rate for register reads
"""

import minimalmodbus
import time
import statistics

# Configuration - match your working setup
COM_PORT = "COM11"
SLAVE_ID = 1
BAUD_RATE = 9600

# Connect
psu = minimalmodbus.Instrument(COM_PORT, SLAVE_ID)
psu.serial.baudrate = BAUD_RATE
psu.mode = minimalmodbus.MODE_RTU
psu.serial.timeout = 0.5
psu.close_port_after_each_call = True

print(f"PSU Speed Test")
print(f"Port: {COM_PORT}, Baud: {BAUD_RATE}")
print("=" * 50)

# Test 1: Single read timing (13 registers)
print("\nTest 1: Measuring single read time (13 registers)...")
read_times = []

for i in range(100):
    start = time.perf_counter()
    try:
        vals = psu.read_registers(0x0001, 13)
        elapsed = time.perf_counter() - start
        read_times.append(elapsed)
    except Exception as e:
        print(f"  Read {i} failed: {e}")

if read_times:
    avg_time = statistics.mean(read_times)
    min_time = min(read_times)
    max_time = max(read_times)
    std_dev = statistics.stdev(read_times) if len(read_times) > 1 else 0
    
    print(f"\n  Samples: {len(read_times)}/100 successful")
    print(f"  Min read time:  {min_time*1000:.1f} ms")
    print(f"  Max read time:  {max_time*1000:.1f} ms")
    print(f"  Avg read time:  {avg_time*1000:.1f} ms")
    print(f"  Std dev:        {std_dev*1000:.1f} ms")
    print(f"\n  Theoretical max rate: {1/avg_time:.1f} Hz")
    print(f"  Safe max rate (avg + 2*std): {1/(avg_time + 2*std_dev):.1f} Hz")

# Test 2: Sustained throughput test
print("\n" + "=" * 50)
print("Test 2: Sustained throughput (10 seconds)...")

successful = 0
failed = 0
start_time = time.perf_counter()
duration = 10.0

while (time.perf_counter() - start_time) < duration:
    try:
        vals = psu.read_registers(0x0001, 13)
        successful += 1
    except:
        failed += 1

elapsed = time.perf_counter() - start_time
actual_rate = successful / elapsed

print(f"\n  Duration: {elapsed:.1f} s")
print(f"  Successful reads: {successful}")
print(f"  Failed reads: {failed}")
print(f"  Actual sustained rate: {actual_rate:.1f} Hz")

# Test 3: Try different baud rates (if supported)
print("\n" + "=" * 50)
print("Test 3: Baud rate comparison...")

baud_rates = [9600, 19200, 38400, 57600, 115200]

for baud in baud_rates:
    psu.serial.baudrate = baud
    
    # Quick test - 20 reads
    times = []
    for _ in range(20):
        try:
            start = time.perf_counter()
            vals = psu.read_registers(0x0001, 13)
            times.append(time.perf_counter() - start)
        except:
            pass
    
    if len(times) >= 10:
        avg = statistics.mean(times)
        print(f"  {baud:6d} baud: {len(times)}/20 success, avg {avg*1000:.1f} ms, ~{1/avg:.1f} Hz")
    else:
        print(f"  {baud:6d} baud: {len(times)}/20 success - unreliable")

# Reset to original
psu.serial.baudrate = BAUD_RATE

print("\n" + "=" * 50)
print("Done!")

