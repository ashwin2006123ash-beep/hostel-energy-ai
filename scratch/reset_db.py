import sqlite3

def reset_rooms():
    conn = sqlite3.connect("hostel_energy.db")
    c = conn.cursor()
    c.execute("""
        UPDATE rooms
        SET power_w = 65.0, current_a = 0.30, voltage_v = 230.2, power_factor = 0.94,
            occupancy_state = 'Occupied', sensor_status = 'ONLINE', room_state = 'NORMAL',
            relay_state = 'CLOSED', switch_state = 'ON', effective_switch_state = 'ON',
            manual_off_lock = 0, fault_status = 'NONE', trip_reason = '',
            persistence_minutes = 0, restoration_eligible = 1,
            last_switch_by = 'System Benchmark Reset'
        WHERE room_id = 'A-102'
    """)
    c.execute("""
        UPDATE rooms
        SET power_w = 145.0, current_a = 0.65, voltage_v = 229.8, power_factor = 0.96,
            occupancy_state = 'Occupied', sensor_status = 'ONLINE', room_state = 'NORMAL',
            relay_state = 'CLOSED', switch_state = 'ON', effective_switch_state = 'ON',
            manual_off_lock = 0, fault_status = 'NONE', trip_reason = '',
            persistence_minutes = 0, restoration_eligible = 1,
            last_switch_by = 'System Benchmark Reset'
        WHERE room_id = 'A-103'
    """)
    conn.commit()
    conn.close()
    print("A-102 and A-103 successfully reset to benchmark normal.")

if __name__ == "__main__":
    reset_rooms()
