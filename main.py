import network
import time
import ujson
from machine import Pin, SoftI2C
from umqtt.simple import MQTTClient
import ssd1306

# --- Cloud & Network Setup ---
WIFI_SSID = "Wokwi-GUEST"
WIFI_PASS = ""
MQTT_BROKER = "broker.hivemq.com"
CLIENT_ID = "esp32-vib-monitor-azhar"
TOPIC_PUB = b"factory/machine1/vibration"
TOPIC_SUB = b"factory/machine1/commands"

# --- Hardware Initialization ---
i2c = SoftI2C(scl=Pin(22), sda=Pin(21))
led_alarm = Pin(2, Pin.OUT)
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

# Initialize MPU6050
MPU_ADDR = 0x68
i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00') # Wake up sensor

def read_raw_data(addr):
    high, low = i2c.readfrom_mem(MPU_ADDR, addr, 2)
    val = (high << 8) | low
    if val > 32768:
        val = val - 65536
    return val

def get_vibration():
    gx = read_raw_data(0x3B) / 16384.0
    gy = read_raw_data(0x3D) / 16384.0
    gz = read_raw_data(0x3F) / 16384.0
    return gx, gy, gz

# --- Boot Sequence ---
oled.fill(0)
oled.text("Connecting WiFi", 4, 25, 1)
oled.show()

wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.connect(WIFI_SSID, WIFI_PASS)
while not wifi.isconnected():
    time.sleep(0.5)

client = MQTTClient(CLIENT_ID, MQTT_BROKER)
client.connect()

# --- Main Loop ---
last_msg_time = time.time()
DANGER_THRESHOLD = 1.50  # Anything above 1.5g is dangerous
flash_state = False

while True:
    client.check_msg()
    
    if time.time() - last_msg_time > 0.5: # Faster 0.5s UI updates
        gx, gy, gz = get_vibration()
        
        # --- 1. Evaluate State & Render "Bigger" UI ---
        if abs(gx) > DANGER_THRESHOLD or abs(gy) > DANGER_THRESHOLD or abs(gz) > DANGER_THRESHOLD:
            system_status = "DANGER"
            led_alarm.value(1)
            flash_state = not flash_state # Toggle flash
            
            # Massive flashing DANGER screen
            if flash_state:
                oled.fill(1) # Solid white screen
                oled.text("!! DANGER !!", 20, 20, 0) # Black text
                oled.text("MOTOR FAULT", 25, 40, 0)
            else:
                oled.fill(0) # Solid black screen
                oled.text("!! DANGER !!", 20, 20, 1) # White text
                oled.text("MOTOR FAULT", 25, 40, 1)
            oled.show()
            
        else:
            system_status = "SAFE"
            led_alarm.value(0)
            
            # High-contrast SAFE dashboard
            oled.fill(0)
            oled.fill_rect(0, 0, 128, 16, 1) # White header banner
            oled.text("STATUS: SAFE", 15, 4, 0) # Black text inside banner
            
            # XYZ Data
            oled.text(f"X: {gx:.2f} g", 5, 25, 1)
            oled.text(f"Y: {gy:.2f} g", 5, 40, 1)
            oled.text(f"Z: {gz:.2f} g", 5, 55, 1)
            oled.show()
        
        # --- 2. Cloud Transmission (Every 2 seconds to avoid spamming) ---
        if time.time() - last_msg_time > 2.0:
            payload = ujson.dumps({
                "machine": "Conveyor_Motor_A",
                "status": system_status,
                "vib_x": round(gx, 2),
                "vib_y": round(gy, 2),
                "vib_z": round(gz, 2)
            })
            
            print(f"Publishing: {payload}")
            client.publish(TOPIC_PUB, payload)
            
        last_msg_time = time.time()
        
    time.sleep(0.1)